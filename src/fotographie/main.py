import bpy
from bpy.props import FloatProperty, EnumProperty, BoolProperty
from bpy.types import PropertyGroup, Panel
from mathutils import *

from math import *
from types import SimpleNamespace as Struct

import inspect

light_meter_panel_states = {}  # "Yes, it's stupid. But it works." --Cllaude

def enum(cls):
    _, line = inspect.getsourcelines(cls)
    counter = 0
    seen = set()
    for name, hint in cls.__annotations__.items():
        value = hint if isinstance(hint, int) else counter
        if value in seen:
            raise ValueError(
                f'Duplicate enum value {value!r} in {cls.__name__} (defined at line {line})'
            )
        seen.add(value)
        setattr(cls, name, value)
        counter = value + 1
    return cls

# Standard camera values
MAX_STEPS = 6

LOWEST_APERTURE_EV = -2
HIGHEST_APERTURE_EV = 15
APERTURE_OFFSET = MAX_STEPS*LOWEST_APERTURE_EV

SLOWEST_SHUTTER_EV = 11
FASTEST_SHUTTER_EV = -16
SHUTTER_OFFSET = MAX_STEPS*SLOWEST_SHUTTER_EV

SLOWEST_ISOSPEED_EV = int(log2(1/64)) # log2(1/64) == -6.0
FASTEST_ISOSPEED_EV = 20 + SLOWEST_ISOSPEED_EV
ISOSPEED_OFFSET = MAX_STEPS*SLOWEST_ISOSPEED_EV


F_NUMBERS = [
  '0.5','',  '0.56',  '0.6' ,  '0.63','',
  '0.7','',  '0.8' ,  '0.85',  '0.9' ,'',
  '1.0','',  '1.1' ,  '1.2' ,  '1.3' ,'',
  '1.4','',  '1.6' ,  '1.7' ,  '1.8' ,'',
  '2.0','',  '2.2' ,  '2.4' ,  '2.5' ,'',
  '2.8','',  '3.2' ,  '3.3' ,  '3.5' ,'',
  '4.0','',  '4.5' ,  '4.8' ,  '5.0' ,'',
  '5.6','',  '6.3' ,  '6.7' ,  '7.1' ,'',
  '8.0','',  '9.0' ,  '9.5' , '10'   ,'',
 '11'  ,'', '13'   , '13.5' , '14'   ,'',
 '16'  ,'', '18'   , '19'   , '20'   ,'',
 '22'  ,'', '25'   , '27'   , '29'   ,'',
 '32'  ,'', '36'   , '38'   , '40'   ,'',
 '45'  ,'', '51'   , '54'   , '57'   ,'',
 '64'  ,'', '72'   , '76'   , '80'   ,'',
 '90'  ,'','101'   ,'107'   ,'114'   ,'',
'128'  ,'','144'   ,'152'   ,'161'   ,'',
'180']

# ▸
APERTURE_LABELS = [(v, f'f/{v}  ', '', 'DOT') for i, v in enumerate(F_NUMBERS)]

STEP_SIZES = [
    ('1', '1 Full Stop', '1.0'), ('2', '1/2 Stop', '0.5'),  ('3', '1/3 Stop', '0.333...'), 
]

RENARD_SERIES = [1.0, 1.25, 1.6, 2.0, 2.5, 3.2, 4.0, 5.0, 6.4, 8.0, 10.0]
EXCEPTIONS = {1: 1.3, 2: 1.5, 5: 3.0, 8: 6.0}  # de facto overrides

DEFAULT_ENUM_IDENT = '-999'
DEFAULT_ENUM_ITEM = (DEFAULT_ENUM_IDENT, 'Reset', '')

@enum
class PANEL_STATE:
    invalid: 0
    closed:  ...
    open:    ...
    closing: ...

def dprint(*args, **kwargs):
    return
    print(*args, **kwargs)

def snapRenard(denom, use_exceptions=1):
    if denom <= 0: return 0
    l = log10(denom)
    k = floor(l)
    index = round((l - k)*10)

    factor = RENARD_SERIES[index]
    if use_exceptions \
    and abs(log2(denom)) < 6.3 \
    and index in EXCEPTIONS:
        factor = EXCEPTIONS[index]

    val = factor*(10**k)
    # print(factor, val)
    return int(val) if k >= 1 else val

def generateShutterSpeeds(self=0, context=0):
    steps = int(self.step_size)
    start = SLOWEST_SHUTTER_EV
    end = FASTEST_SHUTTER_EV
    M = MAX_STEPS//steps

    speeds = [DEFAULT_ENUM_ITEM]
    for si in range(start*MAX_STEPS, end*MAX_STEPS - 1, -M):
        EV_t = si/MAX_STEPS
        sign = 1
        factor = 1
        prefix = ''
        suffix = '"'
        if EV_t >= 6:
            suffix = "'"
            factor /= 60
        elif EV_t <= -1.:
            sign = -1
            prefix = '1/'
            suffix = ''

        s = 2**(sign*EV_t)*1.024

        snapped = snapRenard(s*factor)
        d = 1 if snapped % 1 else None
        snapped = round(snapped, d)
        label = f'{prefix}{snapped}{suffix}'
        identifier = str(si)

        speeds.append((identifier, label, f'{EV_t=:+0.1f}'))
    return speeds

def floor2(v, f):
    s = 10**f
    return floor(v*s)/s

def generateEVIndices(steps=3):
    start, end = (-2*steps, 15*steps + (3 - steps))
    return [a/steps for a in range(start, end, +1)]

def generateApertures(self=0, context=0):
    steps = int(self.step_size)
    filtered = [DEFAULT_ENUM_ITEM]
    for i, a in enumerate(APERTURE_LABELS):
        include = int((i % (MAX_STEPS//steps)) == 0)
        exponent = i + APERTURE_OFFSET
        ev_a = exponent/MAX_STEPS

        if a[0] and include:
            filtered.append((str(exponent), a[1], f'EV_a:{ev_a:0.1f}'))
    return filtered

def generateISOSpeeds(self=0, context=0):
    renard = RENARD_SERIES[:-1]
    all_thirds = []
    step_size = (int(self.step_size)//2)*2 + 1

    n = len(renard)
    factor = 1
    i0 = 3 - step_size
    ev_iso = SLOWEST_ISOSPEED_EV
    if step_size > 2: ev_iso -= 2/3

    index = i0
    ev_range = FASTEST_ISOSPEED_EV - SLOWEST_ISOSPEED_EV
    for i in range((ev_range + 1)*step_size):
        r = renard[index]*factor

        ident = (round(ev_iso*MAX_STEPS))
        if (ev_iso < 6) or ((ident%6) != 0):
            display = (r if r < 4 else round(r))
        else:
            display = round(pow(2, ev_iso)*100)

        stop = (str(ident), str(display), f'EV_iso={round(ev_iso, 1)}')
        all_thirds.append(stop)

        ev_iso += 1/step_size
        index += 3//step_size
        if index >= n:
            index -= n
            factor *= 10

    return [DEFAULT_ENUM_ITEM] + list(reversed(all_thirds))

def isneg(x):
    return 0 if x >= 0 else 1

def evFromPreset(preset):
    if preset == '': preset = 0
    return float(preset)/MAX_STEPS

def aperturePresetFromExponent(exponent):
    ai = exponent*MAX_STEPS
    index = int(ai - APERTURE_OFFSET)
    if index >= len(F_NUMBERS):
        return '00'
    return F_NUMBERS[index]

def apertureFromExponent(preset):
    eva = evFromPreset(preset)
    return pow(2, eva/2)

def shutterFromExponent(preset):
    evt = evFromPreset(preset)
    return pow(2, evt)

def isoSpeedFromExponent(preset):
    evt = evFromPreset(preset)
    return pow(2, evt)*100

def updateAperture(self, context):
    if self.aperture_preset == DEFAULT_ENUM_IDENT:
        self.aperture_preset = f'{5*MAX_STEPS}' # f/6.6
    self.aperture_index = int(self.aperture_preset)
    updateExposure(self, context)

def updateShutter(self, context):
    if self.shutter_preset == DEFAULT_ENUM_IDENT:
        self.shutter_preset = f'{-6*MAX_STEPS}' # 1/60 s
    self.shutter_index = int(self.shutter_preset)
    updateExposure(self, context)

def updateISOSpeed(self:'CameraExposureSettings', context):
    if self.iso_preset == DEFAULT_ENUM_IDENT:
        self.iso_preset = '0'
    self.iso_index = int(self.iso_preset)
    updateExposure(self, context)

def updateStepSize(self, context):
    context.scene.light_meter.panel_state = PANEL_STATE.closed
    ai = self.aperture_index
    si = self.shutter_index
    isoi = self.iso_index
    mod = MAX_STEPS//int(self.step_size)

    self.aperture_preset = str(ai - ai%mod)
    self.shutter_preset = str(si - si%mod)

    if mod == 3: mod = 2 # We don't do ISO speeds in half steps
    self.iso_preset = str(isoi + (-isoi)%mod)

def closePanels():
    states = light_meter_panel_states
    for panel in states:
        if states[panel] == PANEL_STATE.open:
            states[panel] = PANEL_STATE.closing

def updateExposure(self, context):
    '''Update film exposure based on camera settings'''
    meter = context.scene.light_meter
    closePanels()
    # if meter.panel_state == PANEL_STATE.open:
    #     meter.panel_state = PANEL_STATE.closing

    if not getattr(context, 'camera', 0):
        # print('NO CAMERA')
        return

    dprint(f'  UPDATE_EXPOSURE: {context.camera=}')
    camera_data = context.camera
    exps = camera_data.exposure_settings

    f_stop = apertureFromExponent(exps.aperture_preset)
    dprint(f'{f_stop=};')

    # shutter_val = exposure_props.shutter_preset
    # shutter_in_s = float(shutter_val)*1e-3
    shutter_in_s = shutterFromExponent(exps.shutter_preset)
    dprint(f'{shutter_in_s=}')

    if exps.iso_preset == '':
        exps.iso_preset = exps.bl_rna.properties['iso_preset'].default
    iso = isoSpeedFromExponent(exps.iso_preset)
    dprint(f'{iso=}')

    # Apply EV adjustment
    ev_factor = 2**exps.ev_adjustment
    dprint(f'{ev_factor=}')

    # Calculate exposure
    K_sekonic = 12.5
    use_offset = 1
    K_blender = 24.59*2 if use_offset else 1
    K_blender = 340
    # dEV 3.92420
    # 14.245183944702148
    exposure_settings = shutter_in_s/(f_stop**2)
    exposure_settings *= iso/100
    exposure_settings *= ev_factor
    film_exposure = K_blender*exposure_settings
    # film_exposure = exposure_settings

    # Update camera and render settings
    camera_data.dof.aperture_fstop = f_stop
    if context.scene.camera.data == camera_data:
        context.scene.render.motion_blur_shutter = shutter_in_s
        context.scene.cycles.film_exposure = film_exposure
        dprint(f'{film_exposure=}')
    else:
        dprint(f'    {context=}\n    {context.scene=}\n{context.scene.camera=}')
        dprint(f'    {camera_data.id_data=}')

class CameraExposureSettings(PropertyGroup):
    '''Camera exposure settings property group'''
    step_size: EnumProperty(
        name='Step Size',
        items=STEP_SIZES,
        description='Steps size between stops.  Default is 1/3 stop.',
        default='3',
        update=updateStepSize,
    ) # type: ignore

    aperture_index: bpy.props.IntProperty(min=LOWEST_APERTURE_EV*MAX_STEPS,
                                          max=HIGHEST_APERTURE_EV*MAX_STEPS) # type: ignore
    aperture_preset: EnumProperty(
        name='Aperture',
        # items=APERTURE_VALUES,
        items=generateApertures,
        default=0,
        update=updateAperture
    ) # type: ignore

    shutter_index: bpy.props.IntProperty(min=FASTEST_SHUTTER_EV*MAX_STEPS,
                                         max=SLOWEST_SHUTTER_EV*MAX_STEPS) # type: ignore
    shutter_preset: EnumProperty(
        name='Shutter Speed',
        items=generateShutterSpeeds,
        default=0,
        update=updateShutter
    ) # type: ignore

    iso_index: bpy.props.IntProperty(min=SLOWEST_ISOSPEED_EV*MAX_STEPS,
                                     max=FASTEST_ISOSPEED_EV*MAX_STEPS) # type: ignore
    iso_preset: EnumProperty(
        name='ISO',
        items=generateISOSpeeds,
        default=0,
        update=updateISOSpeed
    ) # type: ignore

    ev_adjustment: FloatProperty(
        name='Exposure Compensation',
        description='EC adjustment in stops',
        min=-5.0, max=5.0,
        default=0.0,
        precision=2,
        step=100/3,  # 1/3 stop increments
        update=updateExposure
    ) # type: ignore

    comp_dir: BoolProperty(
        name='Meter Exposure Compensation Direction',
        description="'Additive' for (+EC) brighter, (-EC) darker; 'Subtractive' to reverse EC direction",
        default=True,
    ) # type: ignore

    show_advanced: BoolProperty(
        name='Show Advanced',
        default=False
    ) # type: ignore

def reorderForColumnFlow(items, cols=3):
    '''Reorder items so column_flow produces row-major appearance'''
    filtered = [item for item in items if item[0] != '']

    total = len(filtered)
    rows = (total + cols - 1) // cols

    reordered = []
    for col in range(cols):
        for row in range(rows):
            idx = row*cols + col
            if idx < total:
                reordered.append(filtered[idx])
            else:
                # print(idx)
                reordered.append(('', '-', 'INVALID'))
    return reordered

class ExposureMenuDrawer:
    def __init__(self, prop_name, generator, columns=3):
        self.prop_name = prop_name
        self.generator = generator
        self.columns = columns

    def draw(self, layout, exps):
        items = self.generator(exps)
        reordered = reorderForColumnFlow(items[1:], cols=self.columns)

        flow = layout.column_flow(columns=self.columns)

        for identifier, label, *_ in reordered:
            row = flow.column()
            row.ui_units_y = 0.666

            if identifier == '':
                row.label(text='', icon='BLANK1')
                continue

            parsed = identifier
            if parsed.startswith('-'):
                parsed = parsed[1:]

            exponent = 0
            if parsed.isdigit():
                exponent = int(identifier)

            icon = 'LAYER_USED' if (exponent % MAX_STEPS) == 0 else 'DOT'
            op = row.operator('exposure.set_preset', text=label, icon=icon)
            op.prop_name = self.prop_name
            op.value = identifier


class EXPOSURE_OT_set_preset(bpy.types.Operator):
    bl_idname = 'exposure.set_preset'
    bl_label = 'Set Exposure Preset'
    bl_description = 'Assign a preset value to the camera exposure setting.'

    value: bpy.props.StringProperty() #type:ignore
    prop_name: bpy.props.StringProperty() #type:ignore

    def execute(self, context):
        exps = context.camera.exposure_settings
        setattr(exps, self.prop_name, self.value)
        return {'FINISHED'}


class EXPOSURE_MT_shutter_menu(bpy.types.Menu):
    bl_label = 'Shutter Speed'
    bl_idname = 'EXPOSURE_MT_shutter_menu'

    drawer = ExposureMenuDrawer('shutter_preset', generateShutterSpeeds)

    def draw(self, context):
        exps = context.camera.exposure_settings
        self.drawer.draw(self.layout, exps)


class EXPOSURE_MT_aperture_menu(bpy.types.Menu):
    bl_label = 'Aperture'
    bl_idname = 'EXPOSURE_MT_aperture_menu'

    drawer = ExposureMenuDrawer('aperture_preset', generateApertures)

    def draw(self, context):
        exps = context.camera.exposure_settings
        self.drawer.draw(self.layout, exps)


class EXPOSURE_MT_iso_menu(bpy.types.Menu):
    bl_label = 'ISO Speed'
    bl_idname = 'EXPOSURE_MT_iso_menu'

    drawer = ExposureMenuDrawer('iso_preset', generateISOSpeeds)

    def draw(self, context):
        exps = context.camera.exposure_settings
        self.drawer.draw(self.layout, exps)

class CAMERA_PT_exposure_settings(Panel):
    '''Camera exposure settings panel'''
    bl_label = 'Camera Exposure'
    bl_idname = 'CAMERA_PT_exposure_settings'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    bl_parent_id = 'DATA_PT_camera'

    last_camera = None
    @classmethod
    def poll(cls, context):
        scene = context.scene
        if scene.camera != cls.last_camera:
            # print('DIFFERENT!')
            cls.last_camera = scene.camera
            if scene.camera.data == context.camera:
                ctx = Struct(camera=context.camera, scene=scene)
                bpy.app.timers.register(
                    lambda: updateExposure(None, ctx)
                )
                # print(f' POLL: {ctx.camera=}\n     : {scene.camera=}')
        return context.camera

    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='CAMERA_DATA')

    def draw(self, context):
        global window_start
        layout = self.layout
        camera_data = context.camera
        exps:CameraExposureSettings = camera_data.exposure_settings

        layout.use_property_split = 1
        # layout.use_property_decorate = 0

        # Main exposure triangle
        col = layout.column(align=0)

        # Aperture row
        row = col.row(align=1)
        row.prop_with_menu(exps, 'aperture_preset', text='Aperture',
                           menu='EXPOSURE_MT_aperture_menu')

        # Shutter speed row
        row = col.row(align=1)
        row.use_property_split = 1
        # row.prop(props, 'shutter_preset', text='Shutter Speed')
        # row.label(text='Shutter Speed')
        # chosen = shutterFromExponent(exps.shutter_preset)
        # chosen = snapRenard(1/chosen)
        row.prop_with_menu(exps, 'shutter_preset', text='Shutter Speed',
                              menu='EXPOSURE_MT_shutter_menu')
        # row.menu('EXPOSURE_MT_shutter_menu', text=str(chosen))

        # ISO row
        row = col.row(align=1)
        row.prop_with_menu(exps, 'iso_preset', text='ISO Speed',
                           menu='EXPOSURE_MT_iso_menu')

        # EV adjustment
        col.separator()
        row = col.row()
        row.prop(exps, 'ev_adjustment', text='EC')

        not_active_camera = context.scene.camera.data != camera_data
        # Show current film exposure value
        if context.scene.cycles:
            col.separator()
            exposure_val = context.scene.cycles.film_exposure
            # 9.26 - log2...
            ev_display =  8.44361 - log2(exposure_val) if exposure_val > 0 else 0
            text = f'Scene Film Exposure: {ev_display:+.1f} EV ({exposure_val:.2e})'
            icon = 'FILE_MOVIE'
            if not_active_camera:
                col.alert = 1
                icon = 'UNLINKED'
            # else:
            #     print(self.last_camera)
            col.label(text=text, icon=icon)
            col.alert = 0

        # Advanced toggle
        col.separator()
        col.prop(exps, 'show_advanced', toggle=True)

        if exps.show_advanced:
            box = col.box()
            if not_active_camera:
                box.enabled = 0
                box.alert = 1
                box.label(text='Not Active Scene Camera')
                box.alert = 0
            box.label(text='Scene Exposure Settings:')
            box.prop(camera_data.dof, 'aperture_fstop', text='DOF F-Stop')
            box.prop(context.scene.render, 'motion_blur_shutter', text='Motion Blur Shutter')
            if context.scene.cycles:
                box.prop(context.scene.cycles, 'film_exposure', text='Film Exposure')
            box.separator()
            b2 = box.box()
            b2.scale_y = 0.5
            b2.label(text='Note: common   values   for  camera', icon='INFO')
            b2.label(text='             settings  don\'t  always  match')
            b2.label(text='             mathematically correct values.')
            b2.label(text='        (e.g., `f/22` = √512 ≈ f/22.63)', icon='FORWARD')

def register():
    # bpy.utils.register_class(CameraExposureSettings)
    # bpy.utils.register_class(CAMERA_PT_exposure_settings)
    bpy.types.Camera.exposure_settings = bpy.props.PointerProperty(type=CameraExposureSettings)

def unregister():
    # bpy.utils.unregister_class(CAMERA_PT_exposure_settings)
    # bpy.utils.unregister_class(CameraExposureSettings)
    del bpy.types.Camera.exposure_settings

if __name__ == '__main__':
    register()
