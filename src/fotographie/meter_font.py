import bpy
import blf
import os
from math import *
from .light_meter import (
    confirmPanel,
    calcMeasuredFromEV,
    Metered, MeteredType,
    LIGHTMETER_PT_main_panel as LIGHTMETER_PT,
    LightMeterProperties, aperturePresetFromExponent
)
from .analog_meter import loadFont, FONT_ID
from .gpu_utils import *
from . import logger as log

# Constants
FONT_PATH = f'{os.path.dirname(__file__)}/fonts/OmegaPixel.ttf'
TEXT_SIZE = 52
TEXT_DPI = 72
TEXT_COLOR = (1.0, .9, 0.825, 1.0)
SHADOW_COLOR = (0.1, 0.1, 0.2, 0.25)
# FONT_ID = 0
TOP_OF_DISPLAY = 72 # measured empirically
BASE_ELEM = 28  # pixel height of 1x scale box layout
ICON_LOC = 92
BORDER = 64

font_info = {
#    'font_id': 0,
    'handler': None,
}

def getRegionScale(region):
    if region.height <= 1: return 0    # Hidden!

    # First, calculate the view height in pixels (or width, doesn't matter)
    transform = region.view2d.region_to_view
    _, view_top_pixel = transform(0, region.height)
    _, view_bottom_pixel = transform(0, 1)  # I think this is correct vs `0`
    view_height = view_top_pixel - view_bottom_pixel
    if view_height == 0: return 0

    # Now, we can get the scale factor
    region_scale = region.height/view_height
    return region_scale

def drawText(panel):
    context = bpy.context
    region = context.region
    panel_state = confirmPanel(panel, region.active_panel_category)
    if not panel_state: return

    meter: LightMeterProperties = context.scene.light_meter
    uiscale = context.preferences.view.ui_scale
    # uiscale = context.preferences.system.ui_scale
    _, y = getDisplayPos(region, 1)
    icon_top = y

    m:Metered = calcMeasuredFromEV(meter)
    full = m.snapped
    frac = m.tenths

    match m.type:
        case MeteredType.T:
            factor = 1 if full < 3 else None
            text = f'{round(full, factor)}{m.suffix}'
        case MeteredType.F:
            text = aperturePresetFromExponent(full)
        case MeteredType.ISO:
            text = f'{full}'
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

    v2d = region.view2d
    vpad = 50/uiscale
    pad, _ = v2d.view_to_region(vpad, 0, clip=0)
    rscale = pow(pad/vpad, 0.5)
    y -= (h/2 + 1.5*BASE_ELEM*uiscale)*rscale

    # 1/
    if m.prefix:
        blf.size(FONT_ID, size/2*rscale)
        wp, hp = blf.dimensions(FONT_ID, m.prefix)
        blf.position(FONT_ID, x - wp, y + hp, 0)
        blf.color(FONT_ID, *TEXT_COLOR)
        blf.draw(FONT_ID, m.prefix)

    # main display
    blf.size(FONT_ID, size*rscale)
    blf.position(FONT_ID, x, y, 0)
    blf.color(FONT_ID, *TEXT_COLOR)
    res = blf.draw(FONT_ID, text)
    # print(res)

    # tenths steps
    if meter.tenth_steps:
        blf.size(FONT_ID, size/2*rscale)
        blf.position(FONT_ID, x + w*rscale, y - size*1/6, 0)
        blf.color(FONT_ID, *TEXT_COLOR)
        blf.draw(FONT_ID, str(frac))

    # Vertical MEASURE    
    # Margins and padding
    ui_scale = context.preferences.system.ui_scale
    rscale = getRegionScale(region)
    left_padding = 8*ui_scale
    sidebar_margin = 21*ui_scale*rscale
    
    # Dimensions
    width = region.width - 2*left_padding*rscale - sidebar_margin
    
    # Convert to region pixels
    x, _ = v2d.view_to_region(left_padding, 0, clip=0)
    y = icon_top - 6*rscale

    measure_text = 'MEASURE'
    FONT_R = 0
    blf.size(FONT_R, 10*rscale*ui_scale)
    wp, hp = blf.dimensions(FONT_R, measure_text)
    blf.enable(FONT_R, blf.ROTATION)
    blf.rotation(FONT_R, -pi/2)

    blf.color(FONT_R, *TEXT_COLOR)
    blf.position(FONT_R, width - x/1.5 - hp, y, 0)
    blf.draw(FONT_R, measure_text)

    blf.disable(FONT_R, blf.ROTATION)

REGION_TYPE = 'UI'
def register():
    dha = bpy.types.SpaceView3D.draw_handler_add
    font_info['handler'] = dha(drawText, (LIGHTMETER_PT,), REGION_TYPE, 'POST_PIXEL')
    log.info(f'Meter font handler registered ({REGION_TYPE})')

def unregister():
    handler = font_info.get('handler', 0)
    if handler:
        # log.debug(f'Removing handler {handler}')
        bpy.types.SpaceView3D.draw_handler_remove(handler, REGION_TYPE)
        font_info['handler'] = None
    else:
        log.warning(f'Unable to remove meter font handler: {font_info}')

if __name__ == '__main__':
    register()
