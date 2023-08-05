# -----  MIT license ------------------------------------------------------------
# Copyright (c) 2022 David Lannan

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ------------------------------------------------------------------------

from defoldsync import defoldUtils

# ------------------------------------------------------------------------

modulesNames = ['DefoldSyncUI']

import bpy, time, queue, re, os, json, shutil, math
from bpy_extras.io_utils import axis_conversion
from io import BytesIO

# ------------------------------------------------------------------------

def makeBlockPNG(texture_path, matname, name, col):

    gencolor = (defoldUtils.to_srgb(col[0]), defoldUtils.to_srgb(col[1]), defoldUtils.to_srgb(col[2]), col[3])

    hexname = defoldUtils.toHex(col[0], col[1], col[2], col[3])
    texname = str(matname) + "_" + name + "_" + hexname
    imgw  = 16 
    imgh  = 16
    filename = texture_path + "/" + texname + ".png"

    img = bpy.data.images.new(texname, width=imgw,height=imgh, alpha=True)
    img.file_format = 'PNG'
    img.generated_color = gencolor

    img.filepath_raw = filename
    img.save() 
    return img

# ------------------------------------------------------------------------

def getImageNode( colors, index, mat, name, texture_path ):

  if(not index in colors):
    return None

  color_node = colors[index]

  # Get the link - this should extract embedded nodes too (need to test/check)
  if( color_node.is_linked ):
    link = color_node.links[0]
    link_node = link.from_node
    if link_node and link_node.type == 'TEX_IMAGE':
      imgnode = link_node.image
      if imgnode and imgnode.type == 'IMAGE':
        return imgnode
    elif link_node and link_node.type == 'MIX_RGB':
      if link_node.blend_type == 'MULTIPLY':
        color1node = link_node.inputs['Color1'].links[0].from_node
        color2node = link_node.inputs['Color2'].links[0].from_node

        if index == 'Base Color':
          baseimg = False
          if color2node and color2node.type == 'TEX_IMAGE':
            imgnode = color2node.image 
            if imgnode and imgnode.type == 'IMAGE':
              baseImg = imgnode 
          if color1node and color1node.type == 'TEX_IMAGE':
            lightnode = color1node.image 
            if lightnode and lightnode.type == 'IMAGE' and lightnode.name.endswith('_baked'):

              nodes = mat.node_tree.nodes
              links = mat.node_tree.links
              links.new(color1node.outputs[0],colors['Emission'])

          if baseimg:
            return baseimg

  # Handle metallic roughness and emission if they have just values set (make a little color texture)
  value_materials = ["metallic_color", "roughness_color", "emissive_color", "alpha_map"]
  if(color_node.type == "VALUE") and (name in value_materials):
    col       = color_node.default_value
    # If alpha is default, then base color will use default settings in alpha channel
    if(name == "alpha_map" and col == 1.0):
      return None
    return makeBlockPNG(texture_path, mat.name, name, [col, col, col, col])

  # if the node is a color vector. Make a tiny color png in temp
  # print( str(color_node.type) + "  " + str(color_node.name) + "   " + str(color_node.default_value))
  if((color_node.type == "RGBA" or color_node.type == "RGB") and name == "base_color" ):

    alpha     = 1.0 
    col       = color_node.default_value
    
    # check if this is linked 
    if( color_node.is_linked ):
      link = color_node.links[0]
      link_node = link.from_node
      col = link_node.outputs[0].default_value

    return makeBlockPNG(texture_path, mat.name, name, [col[0], col[1], col[2], alpha])

  return None 

# ------------------------------------------------------------------------

def addTexture( mat, textures, name, color_node, index, texture_path, context ):

  imgnode = getImageNode( color_node, index, mat, name, texture_path )

  if imgnode != None:
    img = imgnode.filepath_from_user()
    basename = os.path.basename(img)
    splitname = os.path.splitext(basename)

    print("[ IMG PATH ] " + str(img))
    print("[ IMG BASE PATH ] " + str(basename))

    if splitname[1] != '.png' and splitname[1] != '.PNG':
      pngimg = os.path.join(texture_path , splitname[0] + ".png")
      if(os.path.exists(pngimg) == False):
        
        imgnode.file_format='PNG' 
        image = bpy.data.images.load(img)

        image_settings = bpy.context.scene.render.image_settings
        image_settings.file_format = "PNG"
        image.file_format='PNG'
        image.save_render(pngimg)
      img = pngimg

    # This is done for internal blender images (embedded)
    if os.path.exists(img) == False:
      img = os.path.join(texture_path , basename)
      image_settings = bpy.context.scene.render.image_settings
      image_settings.file_format = "PNG"
      imgnode.filepath = img
      imgnode.save()
    
    # If this is an image texture, with an active image append its name to the list
    textures[ name ] = img.replace('\\','\\\\')


# ------------------------------------------------------------------------
# Check if a lightmap looks like it has been set

def HasLightmap( color_node ):

  if(not "Emission" in color_node):
    return False

  node = color_node["Emission"]
  if node and len(node.links) > 0:
    link = node.links[0]
    if link:
      link_node = link.from_node
      if link_node:
        print("[EMISSION NAME] " + str(link_node.name))
        if link_node.name.endswith("_Lightmap"):
          return True 
  return False


# ------------------------------------------------------------------------
# Convert Principled BSDF to Our PBR format

def ConvertPrincipledBSDF( thisobj, mat, texture_path, context, config ):

    textures = {}
    lightmap_enable = False

    bsdf = mat.node_tree.nodes["Principled BSDF"] 

    # material names are cleaned here
    mat.name = re.sub(r'[^\w]', ' ', mat.name)
    if(bsdf is not None):

        print("[ BSDF ] : bsdf material type used.")
        addTexture( mat, textures, "base_color", bsdf.inputs, "Base Color", texture_path, context )
        addTexture( mat, textures, "metallic_color", bsdf.inputs, "Metallic", texture_path, context )
        addTexture( mat, textures, "roughness_color", bsdf.inputs, "Roughness", texture_path, context )
        addTexture( mat, textures, "emissive_color", bsdf.inputs, "Emission", texture_path, context )
        addTexture( mat, textures, "emissive_strength", bsdf.inputs, "Emission Strength", texture_path, context )
        addTexture( mat, textures, "normal_map", bsdf.inputs, "Normal", texture_path, context )
        addTexture( mat, textures, "alpha_map", bsdf.inputs, "Alpha", texture_path, context )

        lightmap_enable = HasLightmap( bsdf.inputs )
        if lightmap_enable:
            mat.name = mat.name + "_LightMap"
    else:
        print("[ ERROR ] : Material type is not Principled BSDF.")
        defoldUtils.ErrorLine( config, " Material type is not Principled BSDF: ",  str(mat.name), "ERROR")

    thisobj["matname"] = mat.name

    if(len(textures) > 0):
        thisobj["textures"] = textures

    return thisobj

# ------------------------------------------------------------------------
# Convert Emission Surface Shader to Our PBR format

def ConvertEmissionShader( thisobj, mat, texture_path, context, config ):

    textures = {}
    lightmap_enable = False

    emission = mat.node_tree.nodes["Emission"] 

    # material names are cleaned here
    mat.name = re.sub(r'[^\w]', ' ', mat.name)
    if(emission is not None):

        print("[ BSDF ] : bsdf material type used.")
#        addTexture( mat, textures, "base_color", emission.inputs, "Base Color", texture_path, context )
#        addTexture( mat, textures, "metallic_color", emission.inputs, "Metallic", texture_path, context )
#        addTexture( mat, textures, "roughness_color", emission.inputs, "Roughness", texture_path, context )
        addTexture( mat, textures, "emissive_color", emission.inputs, "Color", texture_path, context )
        addTexture( mat, textures, "emissive_strength", emission.inputs, "Strength", texture_path, context )
#        addTexture( mat, textures, "normal_map", emission.inputs, "Normal", texture_path, context )
#        addTexture( mat, textures, "alpha_map", emission.inputs, "Alpha", texture_path, context )

        lightmap_enable = HasLightmap( emission.inputs )
        if lightmap_enable:
            mat.name = mat.name + "_LightMap"
    else:
        print("[ ERROR ] : Material is not Emission type.")
        defoldUtils.ErrorLine( config, " Material is not Emission type: ",  str(mat.name), "ERROR")

    thisobj["matname"] = mat.name

    if(len(textures) > 0):
        thisobj["textures"] = textures

    return thisobj

# ------------------------------------------------------------------------
# Check material type and convert to something we can export to PBR

node_convert_list = [
    ("Principled BSDF", ConvertPrincipledBSDF, ""),
    ("Emission", ConvertEmissionShader, ""),
]

# node_convert_list["Mix Shader"] = {}
# node_convert_list["Mix Shader"]["mat_type"] = "Mix Shader"
# node_convert_list["Mix Shader"]["Convert"] = ConvertMixShader

# node_convert_list["ColorRamp"] = {}
# node_convert_list["ColorRamp"]["mat_type"] = "ColorRamp"
# node_convert_list["ColorRamp"]["Convert"] = ConvertColorRampShader

def ProcessMaterial( thisobj, mat, texture_path, context, config ):

    if mat is not None and mat.use_nodes:

        for conv in node_convert_list:
            node_type = conv[0]
            if node_type in mat.node_tree.nodes:
                return conv[1]( thisobj, mat, texture_path, context, config )
        
        print("[ ERROR ] : Material type is not supported.")
        defoldUtils.ErrorLine( config, "  Material type is not supported..",  str(mat.name), "ERROR")

    else:
        print("[ ERROR ] : Material type missing or not supported.")
        defoldUtils.ErrorLine( config, " Material type missing or not supported.",  str(mat.name), "ERROR")

    return thisobj
