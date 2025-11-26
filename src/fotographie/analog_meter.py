import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from math import *
import os
from bpy.app.handlers import persistent
from .light_meter import (
    confirmPanel, calcMeasuredFromEV,
    Metered, MeteredType,
    LIGHTMETER_PT_main_panel as LIGHTMETER_PT
)
from .camera import snapRenard
from .gpu_utils import *
from . import logger as log

FONT_PATH = f'{os.path.dirname(__file__)}/fonts/nike-2002-04.ttf'

def loadFont():
    font_id = 0
    if os.path.exists(FONT_PATH):
        loaded = blf.load(FONT_PATH)
        if loaded >= 0:
            font_id = loaded
    else:
        log.warning(f'Analog meter font missing: {FONT_PATH}')
    return font_id

FONT_ID = loadFont()
BOX_THEME = bpy.context.preferences.themes['Default'].user_interface.wcol_box

def drawMeter(x_pos, y_pos, width, height, m:Metered, min_value=-3, max_value=14):
    '''Draw an analog-style exposure meter'''

    current_value = m.ev_value
    mode = m.type
    if mode == MeteredType.T:
    #     min_value = 14
    #     max_value = -3
        current_value *= -1

    # Calculate normalized position for needle (0.0 to 1.0)
    # Using log scale for f-stops
    log2_ = lambda x:x
    log_current = log2_(current_value)
    log_min = log2_(min_value)
    log_max = log2_(max_value)
    normalized_pos = (log_current - log_min)/(log_max - log_min)
    normalized_pos = max(0.0, min(1.0, normalized_pos))
    
    # Define f-stop values to display
    # f_stops = [sqrt(2**(f)) for f in range(-1, 15)][:-1]
    f_stops = range(-2, 14)
    
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Draw background
    pad = 0
    vertices_bg = [
        (x_pos - pad, y_pos),
        (x_pos + width, y_pos),
        (x_pos + width, y_pos + height),
        (x_pos - pad, y_pos + height)
    ]
    indices_bg = [(0, 1, 2), (0, 2, 3)]
    batch_bg = batch_for_shader(shader, 'TRIS', {'pos': vertices_bg}, indices=indices_bg)
    shader.bind()
    bg_color = Vector(BOX_THEME.inner).xyz/1.25
    # bg_color = Vector([0.08627, 0.09411, 0.1255])*1.666
    bg_color.resize_4d()
    shader.uniform_float('color', bg_color)
    batch_bg.draw(shader)
    
    # Draw tick marks
    tick_height = height*0.3
    tick_vertices = []
    tick_indices = []
    idx = 0

    pad = 0
    for i, ev_label in enumerate(f_stops):
        log_stop = log2_(ev_label)
        tick_pos = (log_stop - log_min)/(log_max - log_min)
        tick_x = x_pos + tick_pos*width + pad
        
        # Major tick
        tick_vertices.extend([
            (tick_x, y_pos + height),
            (tick_x, y_pos + height - tick_height)
        ])
        tick_indices.append((idx, idx + 1))
        idx += 2
        
        # Minor ticks between major stops (if space allows)
        if i < len(f_stops) - 1:
            next_stop = f_stops[i + 1]
            log_next = log2_(next_stop)
            count = 2
            for t in range(count):
                t_diff = t*(log_next - log_stop)
                mid_log = (count*log_stop + log_next + t_diff)/(count + 1)
                mid_pos = (mid_log - log_min)/(log_max - log_min)
                mid_x = x_pos + mid_pos*width + pad
                
                minor_tick_height = tick_height*0.5
                tick_vertices.extend([
                    (mid_x, y_pos + height),
                    (mid_x, y_pos + height - minor_tick_height)
                ])
                tick_indices.append((idx, idx + 1))
                idx += 2

    batch_ticks = batch_for_shader(shader,
        'LINES', {'pos': tick_vertices}, indices=tick_indices)
    shader.bind()
    shader.uniform_float('color', (0.666, 0.666, 0.666, 1.0))
    batch_ticks.draw(shader)

    # base line
    tick_vertices = [
        (x_pos, y_pos),
        (x_pos + width, y_pos),
    ]
    tick_indices = [(0, 1)]
    tick_color = Vector((0.275, 0.298, 0.353, 1.0))

    batch_ticks = batch_for_shader(shader,
        'LINES', {'pos': tick_vertices}, indices=tick_indices)
    shader.bind()
    shader.uniform_float('color', tick_color)
    batch_ticks.draw(shader)
    
    # Draw needle/indicator
    needle_x = x_pos + normalized_pos*width + pad
    needle_width = 4
    n_height = height*0.8
    needle_vertices = [
        (needle_x - needle_width/2, y_pos),
        (needle_x + needle_width/2, y_pos),
        (needle_x + needle_width/2, y_pos + n_height),
        (needle_x - needle_width/2, y_pos + n_height)
    ]
    needle_indices = [(0, 1, 2), (0, 2, 3)]
    batch_needle = batch_for_shader(shader, 'TRIS', {'pos': needle_vertices}, indices=needle_indices)
    shader.bind()

    gpu.state.blend_set('ALPHA')
    shader.uniform_float('color', (1.0, 0.4, 0.2, 0.75))
    batch_needle.draw(shader)
    
    # Draw f-stop labels
    font_id = FONT_ID if FONT_ID >= 0 else 0
    blf.color(font_id, 0.8, 0.8, 0.8, 1.0)
    
    # print(current_value)
    for ev_label in f_stops:
        log_stop = log2_(ev_label)
        label_pos = (log_stop - log_min)/(log_max - log_min)
        label_x = x_pos + label_pos*width
        
        # Format label
        match mode:
            case MeteredType.F:
                label = max(0.0, pow(2, ev_label/2))
                if label == int(label) or label >= 10:
                    label_text = str(int(label))
                else:
                    label_text = f'{label:0.1f}'
                    if label_text == '5.7': label_text = '5.6'

                if label < 1.0:
                    # label_text = '\xbd' # unicode:`1/2` (½)
                    label_text = label_text[1:]
                    blf.size(font_id, 16)
            case MeteredType.T:
                sign = -1 if ev_label < 0 else 1
                label = pow(2, sign*ev_label)
                suffix = unit = ''
                if sign < 0:
                    unit = 's'
                shutter = int(snapRenard(label))
                if shutter > 999:
                    suffix = 'k'
                    shutter = int(shutter/1000)
                label_text = f'{shutter}{suffix}{unit}'
            # case MeteredType.ISO:
            #     label = int(pow(2, ev_label))*100
            #     label_text = f'{label}'
            case _:
                label_text = '--'
        
        blf.size(font_id, 14)
        text_width, text_height = blf.dimensions(font_id, label_text)
        blf.position(font_id, label_x - text_width/2 + pad, y_pos + 5, 0)
        blf.draw(font_id, label_text)

DISPLAY_HEIGHT = 102
def drawAnalogMeter(panel):
    context = bpy.context
    region = context.region
    panel_state = confirmPanel(panel, region.active_panel_category)
    if not panel_state:
        return
    meter = context.scene.light_meter
    uiscale = context.preferences.view.ui_scale

    gutter_A = 10
    gutter = 40 + gutter_A
    region_width = (region.width - gutter)/uiscale

    pad = 13/uiscale
    width = (region_width - 2*pad)*0.94
    x = (region_width - width)/2 + gutter_A/uiscale

    height = 30
    _, y = getDisplayPos(region, 1)
    vw, vy = region.view2d.region_to_view(region.width/uiscale, y/uiscale)
    vy -= 1.5*DISPLAY_HEIGHT
    rw, ry = region.view2d.view_to_region((vw - gutter/2)/uiscale, vy, clip=0)
    rscale = region.width/vw/uiscale

    x, y, width, height = [uiscale*V for V in [x, ry, rw, height]]
    drawMeter(x, y, width, height*rscale, calcMeasuredFromEV(meter))

@persistent
def reloadAnalogMeter(filepath=0):
    global FONT_ID
    FONT_ID = loadFont()

handler_info = {
    'handler': None,
    'region_type': 'UI',
}
def register():
    reloadAnalogMeter()
    if reloadAnalogMeter not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(reloadAnalogMeter)

    handler = handler_info['handler']
    REGION_TYPE = handler_info['region_type']
    if handler:
        bpy.types.SpaceView3D.draw_handler_remove(handler, handler_info['region_type'])
    dha = bpy.types.SpaceView3D.draw_handler_add
    handler_info['handler'] = dha(drawAnalogMeter, (LIGHTMETER_PT,), REGION_TYPE, 'POST_PIXEL')
    log.info(f'Analog meter draw handler registered ({REGION_TYPE})')

def unregister():
    if reloadAnalogMeter in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(reloadAnalogMeter)

    handler = handler_info.get('handler')
    if handler:
        bpy.types.SpaceView3D.draw_handler_remove(handler, handler_info['region_type'])
        handler_info['handler'] = None
