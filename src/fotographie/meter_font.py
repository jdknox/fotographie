import bpy
import blf
from math import *
from .light_meter import (
    confirmPanel,
    getDisplayPos,
    calcMeasuredFromEV,
    Metered, MeteredType,
    LIGHTMETER_PT_main_panel as LIGHTMETER_PT,
    LightMeterProperties, aperturePresetFromExponent
)
# from .main import stepTenths

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
    _, y = getDisplayPos(region, 1)

    # ev = meter.ev_value
    # step = 2*log2(ev)
    # ev = round(ev) if ev >= 1000 else round(ev, 1)
    # full = floor(step)
    # frac = round(step - full)
    # full /= 2

    m:Metered = calcMeasuredFromEV(meter)
    full = m.snapped
    frac = m.tenths

    match m.type:
        case MeteredType.T:
            factor = 1 if full < 3 else None
            text = f'{round(full, factor)}{m.suffix}'
        case MeteredType.F:
            text = aperturePresetFromExponent(full)
        case _:
            text = '--'

    size = TEXT_SIZE*uiscale
    pad = size/2
    w = region.width*0.95
    count = 0
    while 1.5*w > (region.width - 4*pad - BORDER*uiscale):
        blf.size(FONT_ID, size)
        w, h = blf.dimensions(FONT_ID, text)
        pad = size/2
        size *= 0.95
        count += 1
        if count > 100:
            break
    # display_height = BASE_ELEM*panel_state.display_scale*uiscale

    x = (0.89*region.width - pad - w)/2
    y -= h/2 + 1.5*BASE_ELEM*uiscale

    # 1/
    if m.prefix:
        blf.size(FONT_ID, size/2)
        wp, hp = blf.dimensions(FONT_ID, m.prefix)
        blf.position(FONT_ID, x - wp, y + hp, 0)
        blf.color(FONT_ID, *TEXT_COLOR)
        blf.draw(FONT_ID, m.prefix)

    # main display
    blf.size(FONT_ID, size)
    blf.position(FONT_ID, x, y, 0)
    blf.color(FONT_ID, *TEXT_COLOR)
    blf.draw(FONT_ID, text)

    # tenths steps
    if meter.tenth_steps:
        blf.size(FONT_ID, size/2)
        blf.position(FONT_ID, x + w, y - size*1/6, 0)
        blf.color(FONT_ID, *TEXT_COLOR)
        blf.draw(FONT_ID, str(frac))

REGION_TYPE = 'UI'
def register():
    dha = bpy.types.SpaceView3D.draw_handler_add
    font_info['handler'] = dha(drawText, (LIGHTMETER_PT,), REGION_TYPE, 'POST_PIXEL')
    print(f'[ADDING]: draw handler: ({drawText.__name__}({LIGHTMETER_PT}); {REGION_TYPE})')

def unregister():
    handler = font_info.get('handler', 0)
    if handler:
        # print(f'REMOVING: {handler=}')
        bpy.types.SpaceView3D.draw_handler_remove(handler, REGION_TYPE)
        font_info['handler'] = None
    else:
        print(f'CANNOT REMOVE! {font_info=}')

if __name__ == '__main__':
    register()
