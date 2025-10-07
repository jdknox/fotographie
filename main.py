import bpy
from bpy.props import FloatProperty, EnumProperty, BoolProperty
from bpy.types import PropertyGroup, Panel
from mathutils import *
from math import log2, sqrt, pow, floor, log10
from types import SimpleNamespace as struct

# Standard camera values
MAX_STEPS = 6
LOWEST_APERTURE_EV = -2
HIGHEST_APERTURE_EV = 15
APERTURE_OFFSET = MAX_STEPS*LOWEST_APERTURE_EV

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
APERTURE_LABELS = [(v, f'· f/{v}  ', '') for v in F_NUMBERS]

SHUTTER_VALUES = [
    ('4096', '1/4000', ''), ('2048', '1/2000', ''), ('1024', '1/1000', ''),
    ('512', '1/500', ''), ('256', '1/250', ''), ('128', '1/125', ''),
    ('64', '1/60', ''), ('32', '1/30', ''), ('16', '1/15', ''),
    ('8', '1/8', ''), ('4', '1/4', ''), ('2', '1/2', ''),
    ('1', '1"', ''), ('2s', '2"', ''), ('4s', '4"', ''), ('CUSTOM', 'Custom', '')
]

ISO_VALUES = [
    ('50', 'ISO 50', ''), ('100', 'ISO 100', ''), ('200', 'ISO 200', ''),
    ('400', 'ISO 400', ''), ('800', 'ISO 800', ''), ('1600', 'ISO 1600', ''),
    ('3200', 'ISO 3200', ''), ('6400', 'ISO 6400', ''), ('12800', 'ISO 12800', ''),
    ('CUSTOM', 'Custom', '')
]

def dprint(*args, **kwargs):
    return
    print(*args, **kwargs)

def generateShutterSpeeds(self=0, context=0):
    labels = [
        '1/64000', '1/32000', '1/16000',
        '1/8000', '1/4000', '1/2000', '1/1000', '1/500', '1/250',
        '1/125', '1/60', '1/30', '1/15', '1/8', '1/4',
        '1/2', '1"', '2"', '4"', '8"', '15"', '30"'
    ]

    speeds = []
    for i in range(21, 0 - 1, -1):
        ms = 2**(i - 6)  # 2^-6 to 2^15 milliseconds
        seconds = str(ms/1000.0)
        label = labels[i]
        identifier = str(ms)  # Use ms value as identifier
        speeds.append((identifier, label, identifier + ' ms'))
    # speeds.append(('CUSTOM', 'Custom', ''))

    return speeds

def floor2(v, f):
    s = 10**f
    return floor(v*s)/s

def generateEVIndices(steps=3):
    start, end = (-2*steps, 15*steps + (3 - steps))
    return [a/steps for a in range(start, end, +1)]

def generateApertures(self=0, context=0):
    steps = 2
    fmt = ' =EV {:+2d}= '
    filtered = []
    if steps == MAX_STEPS:
        filtered = [('0', fmt.format(APERTURE_OFFSET//MAX_STEPS), '')]
    for i, a in enumerate(APERTURE_LABELS):
        include = (i % (MAX_STEPS//steps)) == 0
        exponent = i + APERTURE_OFFSET
        ev_a = exponent/MAX_STEPS
        if a[0] and include:
            sp = ' '*min(1, i % steps)
            new_a = a[1][min(1, i % steps):]
            filtered.append((str(exponent), sp+new_a, f'EV_a:{ev_a:0.1f}'))
        elif (steps == MAX_STEPS) and (i % MAX_STEPS == 5):
            filtered.append(('0', fmt.format(int(ev_a) + 1), ''))
    return filtered

def generateISOSpeeds(self=0, context=0):
    std_100 = [100, 125, 160, 200, 250, 320, 400, 500, 640, 800,]
    all_thirds = []
    for b in range(-2, 4):
        for iso in std_100:
            ident = iso*pow(10, b)
            display = str(ident if ident < 4 else round(ident))
            all_thirds.append((str(ident), display, ''))
    return all_thirds

def isneg(x):
    return 0 if x >= 0 else 1

def evaFromExponent(exponent):
    return float(exponent)/MAX_STEPS

def apertureFromExponent(exponent):
    # index = int(exponent) - APERTURE_OFFSET
    # return float(F_NUMBERS[index])
    eva = evaFromExponent(exponent)
    return pow(2, eva/2)

def updateAperture(self, context):
    # Update other settings
    updateExposure(self, context)

def updateExposure(self, context):
    '''Update film exposure based on camera settings'''
    if not getattr(context, 'camera', 0):
        print('NO CAMERA')
        return

    print(f'  UPDATE_EXPOSURE: {context.camera=}')
    camera_data = context.camera
    exposure_props = camera_data.exposure_settings

    f_stop = apertureFromExponent(exposure_props.aperture_preset)
    print(f'{f_stop=};')

    if exposure_props.shutter_preset == 'CUSTOM':
        shutter_in_s = exposure_props.shutter_custom
    else:
        shutter_val = exposure_props.shutter_preset
        shutter_in_s = float(shutter_val)*1e-3
    dprint(f'{shutter_in_s=}')

    if exposure_props.iso_preset == 'CUSTOM':
        iso = exposure_props.iso_custom
    else:
        iso = float(exposure_props.iso_preset)
    dprint(f'{iso=}')

    # Apply EV adjustment
    ev_factor = 2**exposure_props.ev_adjustment
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
        print(f'{film_exposure=}')
    else:
        dprint(f'    {context=}\n    {context.scene=}\n{context.scene.camera=}')
        dprint(f'    {camera_data.id_data=}')

class CameraExposureSettings(PropertyGroup):
    '''Camera exposure settings property group'''
    aperture_index: bpy.props.IntProperty(min=0, max=len(APERTURE_LABELS)-1) # type: ignore

    aperture_preset: EnumProperty(
        name='Aperture',
        # items=APERTURE_VALUES,
        items=generateApertures,
        default=7,
        update=updateAperture
    ) # type: ignore

    aperture_custom: FloatProperty(
        name='Custom F-Stop',
        min=0.1, max=128.0,
        default=2.8,
        precision=1,
        step=100,
        update=updateExposure
    ) # type: ignore

    shutter_preset: EnumProperty(
        name='Shutter Speed',
        items=generateShutterSpeeds,
        default=10,
        update=updateExposure
    ) # type: ignore

    shutter_custom: FloatProperty(
        name='Custom Shutter',
        min=0.0001, max=30.0,
        default=1.0/60,
        precision=4,
        update=updateExposure
    ) # type: ignore

    iso_preset: EnumProperty(
        name='ISO',
        items=generateISOSpeeds,
        default=20,
        update=updateExposure
    ) # type: ignore

    iso_custom: FloatProperty(
        name='Custom ISO',
        min=25, max=204800,
        default=100,
        precision=0,
        update=updateExposure
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
            print('DIFFERENT!')
            cls.last_camera = scene.camera
            if scene.camera.data == context.camera:
                ctx = struct(camera=context.camera, scene=scene)
                bpy.app.timers.register(
                    lambda: updateExposure(None, ctx)
                )
                print(f' POLL: {ctx.camera=}\n     : {scene.camera=}')
        return context.camera

    def draw_header(self, context):
        layout = self.layout
        layout.label(text='', icon='CAMERA_DATA')

    def draw(self, context):
        global window_start
        layout = self.layout
        camera_data = context.camera
        props = camera_data.exposure_settings

        layout.use_property_split = 1
        # layout.use_property_decorate = 0

        # Main exposure triangle
        col = layout.column(align=0)

        # Aperture row
        row = col.row(align=1)
        row.prop(props, 'aperture_preset', text='Aperture', expand=0)
        if props.aperture_preset == 'CUSTOM':
            row.prop(props, 'aperture_custom', slider=0)

        # Shutter speed row
        row = col.row(align=1)
        row.prop(props, 'shutter_preset', text='Shutter Speed')
        if props.shutter_preset == 'CUSTOM':
            row.prop(props, 'shutter_custom', text='')

        # ISO row
        row = col.row(align=1)
        row.prop(props, 'iso_preset', text='ISO Speed')
        if props.iso_preset == 'CUSTOM':
            row.prop(props, 'iso_custom', text='')

        # EV adjustment
        col.separator()
        row = col.row()
        row.prop(props, 'ev_adjustment', text='EC')

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
        col.prop(props, 'show_advanced', toggle=True)

        if props.show_advanced:
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
