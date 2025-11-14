import bpy
import gpu, bgl
import blf
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from math import *
import sys

NIKE = blf.load('F:/Downloads/Fonts/nike-2002-04.ttf')

def drawMeter(x_pos, y_pos, width, height, current_value, min_value=0.5, max_value=128):
    '''Draw an analog-style exposure meter'''
    
    # Calculate normalized position for needle (0.0 to 1.0)
    # Using log scale for f-stops
    log_current = log2(current_value)
    log_min = log2(min_value)
    log_max = log2(max_value)
    normalized_pos = (log_current - log_min)/(log_max - log_min)
    normalized_pos = max(0.0, min(1.0, normalized_pos))
    
    # Define f-stop values to display
    f_stops = [sqrt(2**(f)) for f in range(-1, 15)][:-1]
    
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
    shader.uniform_float('color', (0.2, 0.2, 0.25, 1.0))
    batch_bg.draw(shader)
    
    # Draw tick marks
    tick_height = height * 0.3
    tick_vertices = []
    tick_indices = []
    idx = 0
    
    for i, f_stop in enumerate(f_stops):
        log_stop = log2(f_stop)
        tick_pos = (log_stop - log_min)/(log_max - log_min)
        tick_x = x_pos + tick_pos*width
        
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
            log_next = log2(next_stop)
            count = 2
            for t in range(count):
                t_diff = t*(log_next - log_stop)
                mid_log = (count*log_stop + log_next + t_diff)/(count + 1)
                mid_pos = (mid_log - log_min)/(log_max - log_min)
                mid_x = x_pos + mid_pos*width
                
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
    shader.uniform_float('color', (0.7, 0.7, 0.7, 1.0))
    batch_ticks.draw(shader)
    
    # Draw needle/indicator
    needle_x = x_pos + normalized_pos*width
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
    sizes = [14, 24]
    half_sizes = [16, 32]
    font_id = 1
    font = NIKE
    if font > 0: font_id = font

    font_size = sizes[font_id] if font_id < len(sizes) else 14
    blf.color(font_id, 0.8, 0.8, 0.8, 1.0)
    
    for f_stop in f_stops:
        log_stop = log2(f_stop)
        label_pos = (log_stop - log_min) / (log_max - log_min)
        label_x = x_pos + label_pos * width
        
        # Format label
        blf.size(font_id, font_size)
        if f_stop == int(f_stop) or f_stop >= 10:
            label_text = str(int(f_stop))
        elif f_stop == 0.5:
            label_text = '\xbd'
            blf.size(font_id, 16)
        else:
            label_text = f'{f_stop:0.1f}'
            if label_text == '5.7': label_text = '5.6'
        
        text_width, text_height = blf.dimensions(font_id, label_text)
        blf.position(font_id, label_x - text_width/2, y_pos + 5, 0)
        blf.draw(font_id, label_text)


def drawCallback():
    '''Callback function for drawing the meter in the UI region'''
    context = bpy.context
    
    # Get the meter value from scene properties
    if hasattr(context.scene, 'meter_value'):
        meter_value = context.scene.meter_value
    else:
        meter_value = 5.6  # Default value
    
    # Position in the UI - you'll need to adjust these based on your panel location
    # These coordinates are in pixel space relative to the region
    x = 64
    y = 100
    width = 340
    height = 42
    
    drawMeter(x, y, width, height, meter_value)


def registerDrawHandler():
    '''Register the draw handler'''
    unregisterDrawHandler()
    draw_handler = bpy.types.SpaceProperties.draw_handler_add(
        drawCallback, (), 'WINDOW', 'POST_PIXEL'
    )
    sys.modules['draw_handler'] = draw_handler


def unregisterDrawHandler():
    '''Unregister the draw handler'''
    draw_handler = sys.modules['draw_handler']
    if draw_handler:
        bpy.types.SpaceProperties.draw_handler_remove(draw_handler, 'WINDOW')
        sys.modules['draw_handler'] = 0


class LIGHTMETER_PT_Panel(bpy.types.Panel):
    '''Light Meter Panel with Analog Display'''
    bl_label = 'Incident Light Meter'
    bl_idname = 'LIGHTMETER_PT_panel'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Exposure settings
        box = layout.box()
        box.label(text='Exposure Settings')
        box.prop(scene, 'meter_value', text='F-Stop')
        
        # Reserve space for the analog meter
        # The actual drawing happens via the draw handler
        box = layout.box()
        box.label(text='Analog Meter Display')
        # Create empty space where the meter will be drawn
        col = box.column()
        col.scale_y = 3.0
        col.label(text='')
        
        layout.separator()
        layout.label(text='Meter draws in region above')

def updateTag(scene, context):
    print(scene, context)

def register():
    NIKE = blf.load('F:/Downloads/Fonts/nike-2002-04.ttf')

    # Register scene property
    bpy.types.Scene.meter_value = bpy.props.FloatProperty(
        name='Meter Value',
        description='Current f-stop reading',
        default=5.6,
        min=0.5,
        max=90.0,
        update=updateTag
    )
    
    bpy.utils.register_class(LIGHTMETER_PT_Panel)
    sys.modules.setdefault('draw_handler', 0)
    registerDrawHandler()


def unregister():
    unregisterDrawHandler()
    bpy.utils.unregister_class(LIGHTMETER_PT_Panel)
    
    # Remove scene property
    del bpy.types.Scene.meter_value


if __name__ == '__main__':
    sys.modules.setdefault('draw_handler', 0)
    unregisterDrawHandler()
    register()
