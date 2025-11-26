import bpy
import gpu
import blf
import imbuf

from mathutils import *
from dataclasses import dataclass as cstruct

import numpy as np
import time
from math import *
from numpy.lib.stride_tricks import sliding_window_view
from gpu_extras.batch import batch_for_shader

def ensureImage(name, width, height):
    if name in bpy.data.images:
        image = bpy.data.images[name]
        image.scale(width, height)
    else:
        image = bpy.data.images.new(name, width, height)
    return image

def savePixelsToImage(array, image_name, max_rows=None):
    if max_rows is not None:
        array = array[:max_rows, :, :]

    height, width, channels = array.shape
    if channels == 1:
        alpha = np.ones((height, width, 1), dtype=array.dtype)
        rgba = np.concatenate((np.repeat(array, 3, axis=2), alpha), axis=2)
    elif channels == 3:
        alpha = np.ones((height, width, 1), dtype=array.dtype)
        rgba = np.concatenate((array, alpha), axis=2)
    else:
        rgba = array

    image = ensureImage(image_name, width, height)
    image.pixels.foreach_set(rgba.flatten())
    image.update()

#def saveBufferToImage(buffer, image_name):
#    height, width, channels = buffer.dimensions
#    image = ensureImage(image_name, width, height)
#    image.pixels.foreach_set(buffer)
#    image.update()

DEBUG_SAVE = 1
def getFrambufferPixels(fb, x, y, w, h, channels=4, type='FLOAT', debug_save=''):
    CH = channels
    x, y, w, h = [int(v) for v in (x, y, w, h)]
    buffer = gpu.types.Buffer(type, int(h*w*CH))

    fb.read_color(x, y, w, h, CH, 0, type, data=buffer)
    pixels = np.frombuffer(buffer, dtype=np.float32).reshape(h, w, CH)
    if DEBUG_SAVE and debug_save:
        savePixelsToImage(pixels, debug_save, max_rows=None)

    return pixels

TEMPLATE = '.template_imgui'
def ensureTemplate(search_text):
    prefs = bpy.context.preferences
    text_style = prefs.ui_styles[0]
    theme_space = prefs.themes[0].view_3d.space

    font_id = 0
    font_size = text_style.panel_title.points*prefs.system.ui_scale
    
    blf.size(font_id, font_size)
    text_width = int(blf.dimensions(font_id, search_text)[0])
    text_height = round(font_size)
#    print(text_width, text_height)

    CHECK = 0
    template_image = bpy.data.images.get(TEMPLATE)
    if CHECK and template_image:
        w, h = template_image.size
        if w == text_width and h == text_height:
            ch = template_image.channels
            buffer = np.empty(w*h*ch, dtype=np.float32)
            template_image.pixels.foreach_get(buffer)
            return buffer.reshape(h, w, ch)

    offscreen = acquireOffscreen(text_width, text_height)
    bg_color = tuple(theme_space.panelcolors.header)
    fg_color = Vector(theme_space.button_title)
    fg_color.resize_4d()

    with offscreen.bind():
        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=bg_color)

        with gpu.matrix.push_pop():
            # Set up pixel coordinates matching offscreen dimensions
            projection = Matrix.OrthoProjection('XY', 4)
            projection = Matrix.Scale(2.0/text_width, 4, X_HAT) @ projection
            projection = Matrix.Scale(2.0/text_height, 4, Y_HAT) @ projection
            projection = Matrix.Translation(Vector((-1, -1, 0))) @ projection
            gpu.matrix.load_matrix(Matrix.Identity(4))
            gpu.matrix.load_projection_matrix(projection)

        blf.position(font_id, 0, 0, 0)
        blf.color(font_id, *fg_color)
        blf.draw(font_id, search_text)

        template_pixels = getFrambufferPixels(fb,
                            0, 0, text_width, text_height,
                            debug_save=TEMPLATE)
    return template_pixels

THRESH_VERTEX_SOURCE = '''
/*in vec2 pos;
in vec2 uv;
out vec2 texCoord;*/
void main()
{
    texCoord = uv;
    gl_Position = vec4(pos.xy, 0.0, 1.0);
}
'''

THRESH_FRAGMENT_SOURCE = '''
/*
out vec4 fragColor;
in vec2 texCoord;
*/

const vec3 LUMA = vec3(0.299, 0.587, 0.114);

void main()
{
    vec2 uv = region_rect.xy + texCoord * region_rect.zw;
    vec3 rgb = texture(source_texture, uv).rgb;
    float luminance = dot(rgb, LUMA);
    float binary = step(threshold_value, luminance);
    fragColor = vec4(binary, 0.0, 0.0, 1.0);
}
'''

g_threshold_shader = None
g_threshold_batch = None

def ensureThresholdShader():
    global g_threshold_shader
    if g_threshold_shader is None:
        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, 'VEC2', 'pos')
        shader_info.vertex_in(1, 'VEC2', 'uv')

        iface = gpu.types.GPUStageInterfaceInfo('imgui_threshold_iface')
        iface.smooth('VEC2', 'texCoord')
        shader_info.vertex_out(iface)

        shader_info.fragment_out(0, 'VEC4', 'fragColor')
        shader_info.sampler(0, 'FLOAT_2D', 'source_texture')
        shader_info.push_constant('VEC4', 'region_rect')
        shader_info.push_constant('FLOAT', 'threshold_value')

        shader_info.vertex_source(THRESH_VERTEX_SOURCE)
        shader_info.fragment_source(THRESH_FRAGMENT_SOURCE)

        g_threshold_shader = gpu.shader.create_from_info(shader_info)
    return g_threshold_shader

def ensureThresholdBatch(shader):
    global g_threshold_batch
    if g_threshold_batch is None:
        positions = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        g_threshold_batch = batch_for_shader(shader, 'TRI_FAN', {'pos': positions, 'uv': uvs})
    return g_threshold_batch

def captureRegionBinary(region, threshold_value=0.5):
    width = int(region.width)
    height = int(region.height)
    if width <= 0 or height <= 0:
        return np.zeros((0, 0), dtype=np.float32)

    framebuffer = gpu.state.active_framebuffer_get()
    region_pixels = getFrambufferPixels(framebuffer,
                                        region.x, region.y,
                                        width, height,
                                        debug_save='region_debug')

    region_pixels = np.ascontiguousarray(region_pixels, dtype=np.float32)
    source_buffer = gpu.types.Buffer('FLOAT',
                                     region_pixels.size,
                                     region_pixels)
    source_texture = gpu.types.GPUTexture((width, height),
                                          format='RGBA32F',
                                          data=source_buffer)

    offscreen = acquireOffscreen(width, height, format='RGBA32F')
    shader = ensureThresholdShader()
    batch = ensureThresholdBatch(shader)

    with offscreen.bind():
        gpu.state.viewport_set(0, 0, width, height)
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('ALPHA')

        shader.bind()
        shader.uniform_sampler('source_texture', source_texture)
        shader.uniform_float('region_rect', (0.0, 0.0, 1.0, 1.0))
        shader.uniform_float('threshold_value', threshold_value)
        batch.draw(shader)
        offscreen_fb = gpu.state.active_framebuffer_get()
        binary_pixels = getFrambufferPixels(offscreen_fb, 0, 0, width, height,
                                            channels=4,
                                            debug_save='region_binary' if DEBUG_SAVE else '')
    return binary_pixels[:, :, 0]

X_HAT:Vector = Vector((1,0,0))
Y_HAT:Vector = Vector((0,1,0))
def findTextInRegion(search_text, region):
    START = time.time()
    ui_scale = bpy.context.preferences.view.ui_scale

    template_pixels = ensureTemplate(search_text)
    template_gray = np.mean(template_pixels[:, :, :3], axis=2)
    template_binary = (template_gray > 0.5).astype(np.float32)
    text_height, text_width, ch = template_pixels.shape
    
    screen_gray = captureRegionBinary(region)
    
    best_match = Vector([-1, -1])
    best_error = float('inf')
    
    PANEL_START = Vector([32, 2])*ui_scale
    start_x = int(PANEL_START.x)
    start_y = int(PANEL_START.y)
    search_height = screen_gray.shape[0] - text_height
    search_width = start_x + text_width

#    return 0,0,time.time() - START
    DO_ERROR_MAP = 0
    if DO_ERROR_MAP: error_map = np.zeros((search_height, search_width), dtype=np.float32)
    template_first_row = template_binary[0, :]
    template_remaining = template_binary[1:, :]
    max_error_value = text_width*text_height
    first_row_threshold = text_width*0.1

    y_indices = range(search_height - 1, start_y - 1, -1)  # iterate from top of region downward
    for y in y_indices:
        row_binary = (screen_gray[y, :] > 0.5).astype(np.float32)
        if row_binary.shape[0] < text_width:
            break

        row_windows = sliding_window_view(row_binary, text_width)
        row_errors = np.sum(np.abs(row_windows - template_first_row), axis=1)
        max_x = min(search_width, row_errors.shape[0])

        for x in range(start_x, max_x):
            first_row_error = row_errors[x]
            if first_row_error > first_row_threshold:
                if DO_ERROR_MAP: error_map[y, x] = max_error_value
                continue

            region_slice = screen_gray[y+1:y+text_height, x:x+text_width]
            region_binary = (region_slice > 0.5).astype(np.float32)
            error = np.sum(np.abs(region_binary - template_remaining))
            error += first_row_error
            if DO_ERROR_MAP: error_map[y, x] = error
            
            if error < best_error:
                best_error = error
                best_match = Vector([x, y])
                print(time.time() - START)
                if best_error < 8:
                    break
        else: # !broak
            continue
        break

    if DO_ERROR_MAP and search_height > 0 and search_width > 0:
        error_min = np.min(error_map)
        error_max = np.max(error_map)
        if error_max > error_min:
            normalized = (error_map - error_min)/(error_max - error_min)
        else:
            normalized = np.zeros_like(error_map)

        error_image = np.repeat(normalized[:, :, None], 4, axis=2)
        error_image[:, :, 3] = 1.0
        savePixelsToImage(error_image, 'imgui_text_error_map')

    ui_best = region.view2d.region_to_view(*best_match)
    match_view = Vector([int(round(val)) for val in ui_best])
    
    max_possible_error = text_width*text_height
    confidence = 1.0 - (best_error/max_possible_error)
    if best_error > max_possible_error:
        match_view *= float('inf')

    print(best_error, confidence, text_width, text_height)
    return match_view, confidence, time.time() - START

@cstruct
class ImguiState:
    draw_handler: int = 0
    counter: int = 0
    offscreen_cache: dict = 0  # (width, height) -> GPUOffScreen

state = bpy.app.driver_namespace.setdefault('imgui_state', ImguiState())

def acquireOffscreen(width, height, format='RGBA32F'):
    if not state.offscreen_cache: state.offscreen_cache = {}

    cache_key = (width, height, format)
    offscreen_cache = state.offscreen_cache
    if cache_key in offscreen_cache:
        return offscreen_cache[cache_key]

    offscreen = gpu.types.GPUOffScreen(width, height, format=format)
    offscreen_cache[cache_key] = offscreen
    return offscreen

def releaseAllOffscreens():
    offscreen_cache = state.offscreen_cache
    for offscreen in offscreen_cache.values():
        offscreen.free()
    offscreen_cache.clear()

ui_region = bpy.context.screen.areas[5].regions[5]
T = 0
N = 1
for i in range(N):
    y, conf, t = findTextInRegion('IMGUI ', ui_region)
    T += t
print('TIMING:', T, T/N)
print(y, conf)
