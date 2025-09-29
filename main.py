import bpy
from bpy.props import FloatProperty, EnumProperty, BoolProperty
from bpy.types import PropertyGroup, Panel
from mathutils import *
from math import log2, sqrt, pow
from types import SimpleNamespace as struct

# Standard camera values
F_STOPS = [0.5, 1.0, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0, 22.0, 32.0, 64.0]
APERTURE_VALUES = [(str(v), f'f/{v}', '') for v in F_STOPS]
# APERTURE_VALUES = [(n, t[2:]+' |', u) for n, t, u in APERTURE_VALUES]

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
        '1/8000', '1/4000', '1/2000', '1/1000', '1/500', '1/250',
        '1/125', '1/60', '1/30', '1/15', '1/8', '1/4',
        '1/2', '1"', '2"', '4"', '8"', '15"', '30"'
    ]

    speeds = []
    for i in range(19):
        ms = 2**(i - 3)  # 2^-3 to 2^15 milliseconds
        seconds = str(ms/1000.0)
        label = labels[i]
        identifier = str(ms)  # Use ms value as identifier
        speeds.append((identifier, label, identifier + ' ms'))
    speeds.append(('CUSTOM', 'Custom', ''))

    return speeds

def generateApertures(self=0, context=0):
    labels = [
        'f/0.5', 'f/0.7', 'f/1.0', 'f/1.4', 'f/2.0', 'f/2.8', 'f/4.0', 'f/5.6',
        'f/8.0', 'f/11', 'f/16', 'f/22', 'f/32', 'f/45', 'f/64', 'f/90'
    ]

    apertures = []
    for i in range(-2, 14):
        fstop = 2**(i/2)  # sqrt(2) progression from f/1.0
        fstop_str = str(round(fstop, 2))
        label = labels[i+2]
        apertures.append((fstop_str, label, f'{fstop:.2f}'))
    apertures.append(('CUSTOM', 'Custom', ''))

    return apertures

def generateISOSpeeds(self=0, context=0):
    std_100 = [100, 125, 160, 200, 250, 320, 400, 500, 640, 800,]
    all_thirds = []
    for b in range(-2, 4):
        for iso in std_100:
            identifier = str(iso*pow(10, b))
            all_thirds.append((identifier, identifier, ''))
    return all_thirds

def OLD_updateAperture(self, context):
    global is_updating, window_start
    if is_updating:
        print('ALREADY UPDATING!')
        return
    else:
        print('UPDATE')
    camera_data = context.scene.camera.data
    exposure_props = camera_data.exposure_settings

    value = exposure_props.aperture_preset
    label = f'f/{value}'
    selected_value = float(value)
    selected_index = APERTURE_VALUES.index((value, label, ''))
    # print(f'{selected_value=} ({selected_index})')

    # Get current window bounds
    start = max(0, window_start - 1)
    end = min(len(APERTURE_VALUES), start + 3)
    if end - start < 3:
        start = max(0, end - 3)
    # print(start, end)

    # Check if selected item is at window edges
    if selected_index == start and window_start > 1:
        # Left edge selected - shift window left
        window_start = max(1, window_start - 1)
    elif selected_index == end - 1 and window_start < len(APERTURE_VALUES) - 2:
        # Right edge selected - shift window right
        window_start = min(len(APERTURE_VALUES) - 2, window_start + 1)
    is_updating = 1
    exposure_props.aperture_preset = APERTURE_VALUES[window_start][0]
    is_updating = 0
    # print(getApertureItems(self, context))

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

    # Get values
    # if exposure_props.aperture_preset == 'CUSTOM':
    #     is_updating = 1
    #     value = exposure_props.aperture_custom
    #     context.scene['value'] = float(value)
    #     # bpy.ops.camera.aperture_knob('INVOKE_REGION_WIN')
    #     step =  round(log2(value)*2 + 1)
    #     F_STOPS = [1.0, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0, 22.0]
    #     f_stop = min(F_STOPS, key=lambda x: abs(x - value))
    #     print(f'{f_stop=}')
    #     #pow(2, (int(step) - 1)/2)
    #     # exposure_props.aperture_custom = f_stop
    #     is_updating = 0
    # else:
    #     is_updating = 1
    #     value = exposure_props.aperture_custom
    #     context.scene['value'] = float(value)
    #     APERTURE_VALUES[0] = (str(drag_updating), f'f/{drag_updating}', '')
    #     drag_updating += 1
    #     # if not drag_updating:
    #     #     bpy.ops.camera.aperture_knob('INVOKE_REGION_WIN')
    if exposure_props.aperture_preset == 'CUSTOM':
        pass
    else:
        f_stop = float(exposure_props.aperture_preset)
    # print(f'{f_stop=}; {{drag_updating=}}')

    if exposure_props.shutter_preset == 'CUSTOM':
        shutter_speed = exposure_props.shutter_custom
    else:
        shutter_val = exposure_props.shutter_preset
        if shutter_val.endswith('s'):
            shutter_speed = 1.0/float(shutter_val[:-1])
        else:
            shutter_speed = 1.0/float(shutter_val)
    dprint(f'{shutter_speed=}')

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
    exposure_settings = shutter_speed/(f_stop**2)
    exposure_settings *= iso/100
    exposure_settings *= ev_factor
    film_exposure = K_sekonic*K_blender*exposure_settings

    # Update camera and render settings
    camera_data.dof.aperture_fstop = f_stop
    if context.scene.camera.data == camera_data:
        context.scene.render.motion_blur_shutter = shutter_speed
        context.scene.cycles.film_exposure = film_exposure
        print(f'{film_exposure=}')
    else:
        dprint(f'    {context=}\n    {context.scene=}\n{context.scene.camera=}')
        dprint(f'    {camera_data.id_data=}')

class CameraExposureSettings(PropertyGroup):
    '''Camera exposure settings property group'''
    aperture_index: bpy.props.IntProperty(min=0, max=len(APERTURE_VALUES)-1) # type: ignore

    aperture_preset: EnumProperty(
        name='Aperture',
        # items=APERTURE_VALUES,
        items=generateApertures,
        default=5,
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
        default=6,
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
            ev_display = 9.26 - log2(exposure_val) if exposure_val > 0 else 0
            text = f'Scene Film Exposure: {exposure_val:.3f} ({ev_display:+.2f} EV)'
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
