import bpy
import blf
from math import *
from .light_meter import confirmPanel, getMeasureButtonPos, calcMeasuredFromEV, \
    LIGHTMETER_PT_main_panel as LIGHTMETER_PT, LightMeterProperties
    

# Constants
TEXT_CONTENT = 'digit_1.png'
TEXT_SIZE = 52
TEXT_DPI = 72
TEXT_COLOR = (1.0, .9, 0.825, 1.0)
SHADOW_COLOR = (0.1, 0.1, 0.2, 0.25)
FONT_ID = 0
TOP_OF_DISPLAY = 72 # measured empirically
BASE_ELEM = 28  # pixel height of 1x scale box layout
ICON_LOC = 92
BORDER = 64

font_info = {
#    'font_id': 0,
    'handler': None,
}

def drawText(panel):
    context = bpy.context
    region = context.region
    panel_state = confirmPanel(panel, region.active_panel_category)
    if not panel_state: return

    meter: LightMeterProperties = context.scene.light_meter
    uiscale = context.preferences.view.ui_scale
    icon_top = int(ICON_LOC*uiscale)
    _, y = getMeasureButtonPos(region, 1)

    label, value_str = calcMeasuredFromEV(meter)
    E = meter.ev_value
    step = 2*log2(E)
    E = round(E) if E >= 1000 else round(E, 1)
    full = floor(step)
    frac = round(step - full)

    text = f'{label, value_str}'

    size = TEXT_SIZE*uiscale
    pad = size/2
    w = region.width
    count = 0
    while 1.5*w > (region.width - pad - BORDER*uiscale):
        blf.size(FONT_ID, size)
        w, h = blf.dimensions(FONT_ID, text)
        pad = size/2
        size *= 0.95
        count += 1
        if count > 100:
            break
    # display_height = BASE_ELEM*panel_state.display_scale*uiscale

    x = (region.width - pad - w)/2
    y -= h/2

    blf.size(FONT_ID, size*2/3)
    blf.position(FONT_ID, x + w, y - size*1/3, 0)
    blf.color(FONT_ID, *TEXT_COLOR)
    blf.draw(FONT_ID, str(frac))

    blf.size(FONT_ID, size)
    blf.position(FONT_ID, x, y, 0)
    blf.color(FONT_ID, *TEXT_COLOR)
    blf.draw(FONT_ID, text)

class TEXT_PT_simple(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '.Light Meter'
    bl_label = 'Display'

    def draw(self, context):
        row = self.layout.column()
        for attr in [
            'bl_context',
            # 'bl_description',
            'bl_idname', 'bl_options',
            'bl_order', 'bl_owner_id', 'bl_parent_id', 'bl_ui_units_x'
        ]:
            row.label(text=f'{attr}: {getattr(self, attr)}')
        # print(self.text)
        # print()

REGION_TYPE = 'UI'
def register():
    # bpy.utils.register_class(TEXT_PT_simple)

    dha = bpy.types.SpaceView3D.draw_handler_add
    font_info['handler'] = dha(drawText, (LIGHTMETER_PT,), REGION_TYPE, 'POST_PIXEL')
    print(f'{font_info=}')

def unregister():
    handler = font_info.get('handler', 0)
    if handler:
        print(f'REMOVING: {handler=}')
        bpy.types.SpaceView3D.draw_handler_remove(handler, REGION_TYPE)
        font_info['handler'] = None
    else:
        print(f'CANNOT REMOVE! {font_info=}')

    # bpy.utils.unregister_class(TEXT_PT_simple)

if __name__ == '__main__':
    register()
