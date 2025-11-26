import bpy
import sys
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from mathutils import *

# Global state (C-style)
g_mouse_x = 0
g_mouse_y = 0
g_mouse_region_x = 0
g_mouse_region_y = 0
g_mouse_clicked = False
g_mouse_down = False
g_hot_item = None
g_active_item = None
g_next_id = 0
g_counter = 0

def resetFrame():
    '''Reset per-frame state'''
    global g_next_id, g_hot_item
    g_next_id = 0
    g_hot_item = None

def getId():
    '''Generate unique ID for widgets'''
    global g_next_id
    id = g_next_id
    g_next_id += 1
    return id

def drawRect(x, y, width, height, color):
    '''Draw a filled rectangle'''
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    vertices = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height)
    ]
    indices = [(0, 1, 2), (0, 2, 3)]
    batch = batch_for_shader(shader, 'TRIS', {'pos': vertices}, indices=indices)
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)

def drawRectOutline(x, y, width, height, color):
    '''Draw rectangle outline'''
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    vertices = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height)
    ]
    indices = [(0, 1), (1, 2), (2, 3), (3, 0)]
    batch = batch_for_shader(shader, 'LINES', {'pos': vertices}, indices=indices)
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)

def drawText(text, x, y, size, color):
    '''Draw text'''
    font_id = 0
    blf.position(font_id, x, y, 0)
    blf.size(font_id, size)
    blf.color(font_id, color[0], color[1], color[2], color[3])
    blf.draw(font_id, text)

def isInside(x, y, width, height):
    '''Check if mouse is inside rectangle'''
    return (x <= g_mouse_x <= x + width and 
            y <= g_mouse_y <= y + height)

def button(label, x, y, width, height):
    '''IMGUI-style button.'''
    global g_hot_item, g_active_item
    
    id = getId()
    mouse_over = isInside(x, y, width, height)
    
    if mouse_over:
        g_hot_item = id
    
    clicked = False
    if g_active_item == id:
        if not g_mouse_down:
            if mouse_over:
                clicked = True
            g_active_item = None
    elif g_hot_item == id:
        if g_mouse_clicked:
            g_active_item = id
    
    # Draw button based on state
    if g_active_item == id:
        drawRect(x, y, width, height, (0.2, 0.4, 0.6, 1.0))
    elif g_hot_item == id:
        drawRect(x, y, width, height, (0.3, 0.5, 0.7, 1.0))
    else:
        drawRect(x, y, width, height, (0.25, 0.3, 0.35, 1.0))
    
    drawRectOutline(x, y, width, height, (0.5, 0.5, 0.6, 1.0))
    drawText(label, x + 10, y + height // 2 - 5, 12, (1.0, 1.0, 1.0, 1.0))
    
    return clicked

def label(text, x, y, size):
    '''IMGUI-style label'''
    getId()
    drawText(text, x, y, size, (1.0, 1.0, 1.0, 1.0))

def panelBegin(x, y, width, height, title):
    '''Begin a panel'''
#    print(f'BEGIN: {x=}, {y=}')
    drawRect(x, y, width, height, (0.2, 0.2, 0.25, 0.9))
    drawRectOutline(x, y, width, height, (0.4, 0.4, 0.5, 1.0))
    drawText(title, x + 10, y + height - 30, 16, (1.0, 1.0, 1.0, 1.0))

def panelEnd():
    '''End a panel'''
    pass

def drawCallback(op, context):
    global g_counter
    try: ui_region = context.region
    except:pass
    x, y = op.mouse_pos
    string = f'{x=}; {ui_region.x=}; {x - ui_region.x}'
    try:
        context.scene['region_x'] = string
    except:pass

    return    
    resetFrame()

    # Panel in view space (will scroll with sidebar)
    panel_view_x = 10
    panel_view_y = 100
    panel_width = ui_region.width - 20
    panel_height = 400

    # Transform to region pixel space
    panel_x, panel_y = ui_region.view2d.view_to_region(
        panel_view_x, panel_view_y, clip=0)
    panelBegin(panel_x, panel_y, panel_width, panel_height, 'IMGUI Panel')
    
    label('Click counter:', panel_x + 20, panel_y + 320, 12)
    label('Count: ' + str(g_counter), panel_x + 20, panel_y + 290, 12)
    
    if button('Increment', panel_x + 20, panel_y + 240, 260, 40):
        g_counter += 1
        print('Counter: ' + str(g_counter))
    
    if button('Reset', panel_x + 20, panel_y + 180, 260, 40):
        g_counter = 0
        print('Counter reset')
    
    if button('Add Cube', panel_x + 20, panel_y + 120, 260, 40):
        bpy.ops.mesh.primitive_cube_add()
        print('Cube added')
    
    if button('Close Panel', panel_x + 20, panel_y + 20, 260, 40):
        cancelOperator(context, bl_panel)
    
    panelEnd()

def cancelOperator(context, panel):
    unregisterDrawHandler(panel)
    context.area.tag_redraw()

def V2(init=0):
    return Vector(init) if init else Vector().to_2d()

class OBJECT_OT_imgui_operator(bpy.types.Operator):
    bl_idname = 'object.imgui_panel'
    bl_label = 'IMGUI Panel'
    bl_options = {'REGISTER'}
    bl_region = 'UI'
    
    draw_handler = None
    mouse_pos = V2()
    
    def modal(self, context, event):
        global g_mouse_x, g_mouse_y, g_mouse_clicked, g_mouse_down
        context.area.tag_redraw()
        region = context.region
        
        # Convert mouse from window coords to UI region coords
        # Transform to view space (accounts for scrolling)
#        print(f'{event.mouse_x} - {region.x} == {event.mouse_x - region.x}')
        self.mouse_pos = event.mouse_region_x, event.mouse_region_y
#        region.view2d.region_to_view(
#            event.mouse_x - region.x,
#            event.mouse_y - region.y
#        )
#        self.x = g_mouse_x

        g_mouse_clicked = (event.type == 'LEFTMOUSE' and event.value == 'PRESS')
        
        if event.type == 'LEFTMOUSE':
            g_mouse_down = (event.value == 'PRESS')
        
        # Check if mouse is over panel area
        mouse_over_panel = isInside(10, 100, region.width - 20, 400)
        
        if g_mouse_clicked and mouse_over_panel:
            return {'RUNNING_MODAL'}
        
        if event.type == 'ESC':
            cancelOperator(context, self)
            return {'CANCELLED'}
        
        return {'PASS_THROUGH'}
    
    def invoke(self, context, event):
        global g_counter

        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, 'View3D not found')
            return {'CANCELLED'}
        
        g_counter = 0
        args = (self, context)
        self.draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            drawCallback, args, 'UI', 'POST_PIXEL')
        print(f'   [ADDING]: {self.draw_handler}')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        cancelOperator(context, self)

def displayBox(context, box, x, y):
    region = context.region

    box.label(text=f'coords:<{x},{y}>')
#    vx, vy = region.view2d.region_to_view(x, y)
##    vx -= region.x
#    box.label(text=f'view coords:<{vx:.0f},{vy:.0f}>')
#    rx, ry = region.view2d.view_to_region(vx, vy, clip=1)
#    box.label(text=f'ui coords:<{rx},{ry}> (clipped)')
#    rx, ry = region.view2d.view_to_region(vx, vy, clip=0)
#    box.label(text=f'ui coords:<{rx},{ry}>')

    for region in context.area.regions:
        if region.type not in {'WINDOW', 'UI'}: continue
        box.label(text=region.type)
        box.label(text=f'{region.x=}, {region.width=}')


class VIEW3D_PT_imgui_panel(bpy.types.Panel):
    bl_label = 'IMGUI Panel Demo'
    bl_idname = 'VIEW3D_PT_imgui_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'
    
    def draw(self, context):
        layout = self.layout
        layout.operator('object.imgui_panel', text='Open IMGUI Panel')

        row = layout.row()
        if 1:
#            print(context.region.type)
            col = row.column()
            col.label(text='Window:')
            box = col.box()
#            displayBox(context, box, g_mouse_x, g_mouse_y)

            col = row.column()
            col.label(text=f'Region:')
            box = col.box()
#            print(f'{g_mouse_x=}; {context.region.x=}')
            displayBox(context, box, g_mouse_x, g_mouse_y)

def unregisterDrawHandler(panel=0):
    if panel:
        if panel.draw_handler:
            bpy.types.SpaceView3D.draw_handler_remove(panel.draw_handler, 'UI')
            panel.draw_handler = 0
    else:
        old_module = sys.modules[__name__]
        panel = getattr(old_module, 'OBJECT_OT_imgui_panel', 0)
        if panel and panel.draw_handler:
            print(f'   REMOVING: {panel.draw_handler}')
            bpy.types.SpaceView3D.draw_handler_remove(panel.draw_handler, 'UI')
            panel.draw_hadler = 0

def register():
    # Clean up handler from previous script run
    unregisterDrawHandler()

    bpy.utils.register_class(OBJECT_OT_imgui_operator)
    bpy.utils.register_class(VIEW3D_PT_imgui_panel)

def unregister():
    unregisterDrawHandler()
    
    bpy.utils.unregister_class(OBJECT_OT_imgui_operator)
    bpy.utils.unregister_class(VIEW3D_PT_imgui_panel)

if __name__ == '__main__':
    register()
