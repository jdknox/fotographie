#

import bpy
import gpu
import json, time
import numpy as np
from mathutils import *
from math import *
from bpy.props import *

from .main import generateApertures, generateShutterSpeeds, CameraExposureSettings

LAYOUT_PADDING_PIXELS = {
    'LAYOUT_BOX': -1,
    'LAYOUT_COLUMN': 5,
    'LAYOUT_ROOT': 10,
    'LAYOUT_ROW': 0,
}

def findBlueRun(buf_u8, w, h, run_len=3, target=(0x70, 0xB2, 0xFF)):
    ch = buf_u8.dimensions[0] // (w*h)
    target_rgb = np.array(target, dtype=np.uint8)
    arr = np.asarray(buf_u8, dtype=np.uint8).reshape(h, w, ch)

    if w < run_len:
        return -1, -1

    window = np.ones(run_len, dtype=np.uint8)
    y = h - 1
    while y >= 0:
        row = arr[y, :, :3]
        matches = np.all(row == target_rgb, axis=1).astype(np.uint8)
        if matches.any():
            hits = np.convolve(matches, window, mode='valid')
            x = np.flatnonzero(hits >= run_len)
            if x.size:
                return int(x[0]), int(y)
        y -= 1
    return -1, -1


def getDisplayPos(region, is_handler=0):
    T = bpy.data.texts
    I = bpy.data.images

    fb = gpu.state.active_framebuffer_get()
    if is_handler:
        x, y, w, h = fb.viewport_get()
    else:
        x = region.x
        y = region.y
        w = region.width
        h = region.height

    # print(f'{fb.viewport_get()=}; <{x=}, {y=}> <{w=}, {h=}>')
    b_type = 'UBYTE'
    ch = 4
    data = gpu.types.Buffer(b_type, w*h*ch)    
    fb.read_color(x, y, w, h, ch, 0, b_type, data=data)
    start = time.perf_counter()
    pos = findBlueRun(data, w, h)

    if 0:
        rgb = np.asarray(data, dtype=np.float32)/255
        if ch == 3:
            rgb = rgb.reshape(-1, 3)
            alpha = np.ones((rgb.shape[0], 1), dtype=rgb.dtype)
            rgba = np.hstack((rgb, alpha)).reshape(-1)
        else:
            rgba = rgb
        name = 'RegionCapture'
        img = I.get(name) or I.new(name=name, width=w, height=h)
        if list(img.size) != [w, h]:
            I.remove(img)
            img = I.new(name=name, width=w, height=h)
        img.pixels.foreach_set(rgba)
    elapsed = time.perf_counter() - start
    # print(f'{pos=} (took {elapsed*1000:0.1f} ms)')
    return pos

# ==========================
def makeAngles(h, w, phi_span=pi):
    j = np.arange(h, dtype=np.float32) + 0.5
    i = np.arange(w, dtype=np.float32) + 0.5

    # elevation ε: +pi/2 .. -pi/2 (top..bottom)
    elev = 0.5*pi - (pi*j/h)
    # azimuth φ: centered left..right over span
    phi_min = -phi_span/2
    phi_max = phi_span/2
    azim = phi_min + (phi_max - phi_min)*i/w

    return elev, azim

def weightsIrradiance(h, w, phi_span=pi):
    elev, azim = makeAngles(h, w, phi_span)
    cos_e = np.cos(elev)
    cos_p = np.abs(np.cos(azim))
    # global cosine law (n·ω) = cosε*cosφ
    cos_theta = np.outer(cos_e, cos_p)
    # solid-angle density for equirect (ε,φ): dω = cosε dε dφ
    d_omega = cos_e[:, None]
    weights = cos_theta * d_omega

    return weights

def measureIlluminance(img, cam_data):
    h, w = img.size
    span = (cam_data.longitude_max - cam_data.longitude_min)
    # span = pi
    weights = weightsIrradiance(h, w, span)

    buf = np.empty(w*h*4, dtype=np.float32)
    img.pixels.foreach_get(buf)

    px = buf.reshape(h, w, 4)[:, :, :3]  # RGB

    num = np.einsum('ij,ijc->c', weights, px, dtype=np.float64)
    den = np.sum(weights, dtype=np.float64)

    CIE = np.array([0.2126, 0.7152, 0.0722])
    E_rgb = 683*pi * num/den*CIE

    return E_rgb

# ===== Sekonic-style exposure helpers =====
def getShutterMilliseconds(meter):
    ms = float(meter.exposure_settings.shutter_preset)
    return ms
    idx = meter.t_index
    SHUTTER_VALUES = generateShutterSpeeds()
    if idx < 0 or idx >= len(SHUTTER_VALUES):
        return 1/125
    return SHUTTER_VALUES[idx][3]

def getShutterSeconds(meter):
    s = getShutterMilliseconds(meter)/1000
    return s

def getFStop(meter):
    return float(meter.exposure_settings.aperture_preset)
    idx = meter.f_index
    F_STOPS = generateApertures()
    if idx < 0 or idx >= len(F_STOPS):
        return 4*sqrt(2)
    return F_STOPS[idx][3]

def formatShutter(t):
    if t < 1:
        denom = int(round(1/t))
        return f'1/{denom}'
    return f'{t:.1f}s'

def calcMeasuredFromEV(meter):
    # EV at current ISO, using: EV_S = log2(N^2/t) - log2(S/100)
    ev = meter.ev_value
    S = float(meter.exposure_settings.iso_preset)
    k = (S/100.0)
    if ev <= -9.9:
        return ('—', '—')

    if meter.mode == 'T':
        # Inputs: T + ISO -> measure F
        t = getShutterSeconds(meter)
        N = sqrt(t * (2**ev) * k)
        # print(f'{t=}; {N=}')
        return ('F', f'{N:.1f}')
    if meter.mode == 'F':
        # Inputs: F + ISO -> measure T
        N = getFStop(meter)
        t = (N*N) / ((2**ev) * k)
        # print(f'{t=}; {N=}')
        return ('T', formatShutter(t))
    # TF: Inputs: T + F -> measure ISO
    t = getShutterSeconds(meter)
    N = getFStop(meter)
    S_meas = 100.0 * ((N*N)/t) / (2**ev)
    S_meas = max(3, min(409600, S_meas))
    return ('ISO', f'{int(round(S_meas))}')

# ============= OPERATOR =============

class LIGHTMETER_OT_measure(bpy.types.Operator):
    '''Measure incident light at 3D cursor position'''
    bl_idname = 'lightmeter.measure'
    bl_label = 'Measure Light'
    bl_options = {'REGISTER', 'UNDO'}

    panel = 0
    def invoke(self, context, event):
        self.panel = LIGHTMETER_PT_main_panel
        region = 0
        for r in context.area.regions:
            if r.type == 'UI':
                region = r
        # x, y = getMeasureButtonPos(region)
        state = setPanelMeasuring(self.panel)
        bpy.app.timers.register(lambda: self.execute(context), first_interval=0.1)
        # res = self.execute(context)
        return {'FINISHED'}

    def execute(self, context):
        scene = context.scene
        meter = scene.light_meter

        # Create or get dome camera
        cam_name = '.LightMeterCamera'
        if cam_name not in bpy.data.objects:
            cam_data = bpy.data.cameras.new(name=cam_name)
            cam_data.display_size = 0.0625
            cam_obj = bpy.data.objects.new(name=cam_name, object_data=cam_data)
            context.collection.objects.link(cam_obj)
            # Position camera at 3D cursor
            cam_obj.location = scene.cursor.location
            cam_obj.rotation_euler = (pi/2, 0, 0)  # Point forward
        else:
            cam_obj = bpy.data.objects[cam_name]
        cam_data = cam_obj.data
        cam_data.type = 'PANO'
        cam_data.panorama_type = 'EQUIRECTANGULAR'
        cam_data.clip_end = 1000.0
        cam_data.clip_start = 0.01171875
        cam_data.latitude_min = -pi/2
        cam_data.latitude_max = pi/2
        half_a = meter.dome_fov/2
        cam_data.longitude_min = -half_a*pi/180
        cam_data.longitude_max = -cam_data.longitude_min

        # Create temp scene for rendering
        temp_scene = scene.copy()
        temp_scene.name = f'.lightmeter_{hex(id(temp_scene))}'

        try:
            # Configure render settings
            temp_scene.camera = cam_obj
            temp_scene.cycles.samples = meter.sample_count
            temp_scene.cycles.film_exposure = 1.0
            temp_scene.render.resolution_x = meter.resolution
            temp_scene.render.resolution_y = meter.resolution
            temp_scene.render.resolution_percentage = 100

            # Render
            bpy.ops.render.render(scene=temp_scene.name, write_still=False)

            # Get measurement
            if 'Viewer Node' in bpy.data.images:
                img = bpy.data.images['Viewer Node']
                E_rgb = measureIlluminance(img, cam_data)
                E = sum(E_rgb)

                # Store results
                meter.illuminance = E
                meter.illuminance_rgb = E_rgb

                # Calculate EV
                iso_speed = float(meter.exposure_settings.iso_preset)
                ESC = E*iso_speed/meter.calibration_constant
                meter.ev_value = log2(ESC) if ESC > 0 else -10

        finally:
            bpy.data.scenes.remove(temp_scene)
            state = setPanelMeasuring(self.panel, 0)

        return {'FINISHED'}

# ============= UI PANEL =============

class LIGHTMETER_PT_main_panel(bpy.types.Panel):
    '''Creates a Panel in the 3D viewport sidebar'''
    bl_label = 'Incident Light Meter'
    bl_idname = 'LIGHTMETER_PT_main_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Light Meter'
    bl_order = -1
    # bl_category = 'Text'
    bl_hash = id(bl_idname)

    # def __init__(self, clas):
    #     super().__init__(clas)
    #     layout = self.layout
    #     print( '  I###', self.bl_category)
    #     print(f'   I## {layout.activate_init=}; {layout.active=}; {layout.enabled=}')
    #     # layout.enabled = 0

    def draw_header(self, context):
        markPanelState(type(self), 0)
        layout = self.layout
        layout.label(text='', icon='SCENE')
        # layout.operator('lightmeter.measure', text='Measure', icon='SCENE')

    def draw(self, context):
        layout = self.layout
        meter = context.scene.light_meter
        markPanelState(type(self), 1)

        # === Settings bar (T/F/ISO) ===
        set_box = layout.box()
        set_row = set_box.row(align=0)
        set_row.scale_y = 1.2

        exps = meter.exposure_settings
        if meter.mode != 'F':
            c1 = set_row.column(align=True)
            c1.label(text='T')
            ms = getShutterMilliseconds(meter)
            str_ms = f'{ms:0.0f}' if ms >= 1.0 else f'{ms}'
            c1.prop(exps, 'shutter_preset', text='')
            c1.box().label(text=f'{str_ms} ms')

        if meter.mode != 'T':
            c1 = set_row.column(align=True)
            c1.label(text='F')
            c1.prop(exps, 'aperture_preset', text='')
            c1.box().label(text=f'{getFStop(meter):.1f}')

        if meter.mode != 'TF':
            c2 = set_row.column(align=True)
            c2.label(text='ISO')
            c2.prop(exps, 'iso_preset', text='')
            c2.box().label(text=f'{exps.iso_preset}')

        # === Big readout (measured value) ===
        disp = layout.split(factor=0.89)
        big = disp.box()
        big.scale_y = 4
        big.alignment = 'EXPAND'
        big.label(icon='NODE_SOCKET_STRING')

        # Your blf drawing code goes here
        measure = disp.row(align=1)
        state = getPanelState(LIGHTMETER_PT_main_panel)
        measuring = state.measuring

        button = measure.column(align=1)
        button.alignment = 'EXPAND'
        button.scale_y = 4.6
        button.operator('lightmeter.measure',
                         text=' ', icon='THREE_DOTS', depress=measuring)

        label = measure.column(align=1)
        label.scale_y = 0.656
        # label.alignment = 'LEFT'
        # label.label(text='M', icon='EVENT_M')
        for c in 'MEASURE':
            label.operator('lightmeter.measure', text=c,
                           emboss=1, depress=measuring)

        button = measure.column(align=1)
        button.alignment = 'RIGHT'
        button.scale_y = 4.6
        button.scale_x = 0.5
        button.operator('lightmeter.measure',
                         text='', emboss=1, depress=measuring)

        # === Analog scale (-3 to +3 EV) ===
        # scale_box = layout.box()
        
        # # Scale labels
        # labels = scale_box.row(align=True)
        # labels.scale_y = 0.9
        # marks = ['-3', '-2', '-1', '0', '1', '2', '3']
        # for m in marks:
        #     labels.label(text=m)

        # # Indicator position
        # indicator = scale_box.row(align=True)
        # idx = 3
        # if meter.ev_value > -9.9:
        #     frac = meter.ev_value - floor(meter.ev_value)
        #     shift = int(round(frac * 3))
        #     idx = max(0, min(6, 3 + shift))
        
        # for i in range(7):
        #     if i == idx:
        #         indicator.label(text='|', icon='KEYFRAME_HLT')
        #     else:
        #         indicator.label(text=' ')

        # Settings
        settings_box = layout.box()
        settings_box.label(text='Settings:', icon='PREFERENCES')

        settings_col = settings_box.column(align=True)
        settings_col.prop(exps, 'iso_preset')
        settings_col.separator()
        settings_col.prop(meter, 'calibration_constant')
        settings_col.prop(meter, 'dome_fov')
        settings_col.prop(meter, 'resolution')
        settings_col.prop(meter, 'sample_count')
        settings_col.prop(meter, 'show_rgb')
        dump_op = settings_col.operator('lightmeter.dump_panel_layout', text='Export Panel Layout', icon='TEXT')
        dump_op.layout_json = repr(layout.introspect()[0])

# ============= PROPERTIES =============

class LightMeterProperties(bpy.types.PropertyGroup):
    illuminance: FloatProperty(
        name='Illuminance',
        description='Measured illuminance in lux',
        default=0.0,
        min=0.0,
        precision=1
    )

    illuminance_rgb: FloatVectorProperty(default=[0.0]*3)

    ev_value: FloatProperty(
        name='EV',
        description='Exposure Value at current ISO',
        default=-10.0,
        precision=1
    )

    calibration_constant: FloatProperty(
        name='Calibration Constant',
        description='Meter calibration constant (340 for lumisphere, 250 for flat, 12.5 for reflected)',
        default=340,
        min=10,
        max=500
    )

    dome_fov: FloatProperty(
        name='Lumisphere FOV',
        description='Meter lumisphere dome angle of view (typically 180°-220°)',
        default=180,
        min=1,
        max=220
    )

    resolution: IntProperty(
        name='Resolution',
        description='Measurement resolution (higher = more accurate)',
        default=2048,
        min=128,
        max=8192
    )

    sample_count: IntProperty(
        name='Samples',
        description='Render samples for measurement',
        default=16,
        min=1,
        max=4096
    )

    show_rgb: BoolProperty(
        name='Show RGB',
        description='Display RGB channel breakdown',
        default=False
    )

    # Sekonic mode + settings
    mode: EnumProperty(
        name='Mode',
        description='Ambient Light mode',
        items=[
            ('T', 'T Priority', 'Shutter priority (measure F)'),
            ('F', 'F Priority', 'Aperture priority (measure T)'),
            ('TF', 'TF Priority', 'T+F priority (measure ISO)'),
        ],
        default='T'
    )

    exposure_settings: PointerProperty(type=CameraExposureSettings)

    tenth_steps: BoolProperty(
        name='Show 1/10 Steps',
        default=True
    )


class LIGHTMETER_OT_dump_panel_layout(bpy.types.Operator):
    bl_idname = 'lightmeter.dump_panel_layout'
    bl_label = 'Dump Panel Layout'
    bl_options = {'INTERNAL'}

    layout_json: StringProperty(default='') # type: ignore

    def execute(self, context):
        stupid = self.layout_json.replace("'", '"')
        layout_data = json.loads(stupid)
        padding = []
        collectLayoutTypes(layout_data, padding)

        text = bpy.data.texts.get('panel_layout.json')
        if text is None:
            text = bpy.data.texts.new('panel_layout.json')
        text.clear()
        formatted_layout = json.dumps(layout_data, indent=2).replace('"', "'")
        text.write(formatted_layout)
        text.write('\n\n')
        text.write(str(padding))
        return {'FINISHED'}

class LightMeterPanelState(bpy.types.PropertyGroup):
    panel_category: StringProperty(default='') #type:ignore
    is_open: BoolProperty(default=False) #type:ignore
    measuring: BoolProperty(default=False) #type:ignore

# ============= REGISTRATION =============

classes = [
    LightMeterPanelState,
    LightMeterProperties,
    LIGHTMETER_OT_measure,
    LIGHTMETER_OT_dump_panel_layout,
    LIGHTMETER_PT_main_panel,
]

def confirmPanel(panel, current_category):
    wm = bpy.context.window_manager
    state = wm.light_meter_panels.get(panel.bl_idname, 0)
    if state and state.is_open:
        if current_category == state.panel_category:
            return state
        else:
            return 0

def getPanelState(panel):
    wm = bpy.context.window_manager
    state = wm.light_meter_panels.get(panel.bl_idname, 0)
    if not state:
        state = wm.light_meter_panels.add()
        state.name = panel.bl_idname
        state.panel_category = panel.bl_category
    return state

def markPanelState(panel, is_open, display_scale=0, measure_scale=0):
    state = getPanelState(panel)
    state.is_open = is_open
    state.display_scale = display_scale
    state.measure_scale = measure_scale

def setPanelMeasuring(panel, is_measuring=1):
    state = getPanelState(panel)
    state.measuring = is_measuring
    return state

def ensureUniquePanelIdname():
    panel = LIGHTMETER_PT_main_panel
    existing = 0
    for attr in dir(bpy.types):
        candidate = getattr(bpy.types, attr)
        if candidate is bpy.types.Panel: continue
        if isinstance(candidate, type) and issubclass(candidate, bpy.types.Panel):
            if candidate.bl_rna.name == panel.__name__:
                panel = candidate
                existing += 1
                continue
            if candidate.bl_space_type == 'VIEW_3D' \
                and candidate.bl_region_type == 'UI' \
                and candidate.bl_category == panel.bl_category \
            :
                existing += 1

    base_id = panel.bl_category
    if existing <= 1:
        print('SAFE')
        return

    suffix = 10
    new_category = f'.{base_id}'
    panel.bl_category = new_category
    bpy.utils.unregister_class(panel)
    bpy.utils.register_class(panel)

def register():
    # ensureUniquePanelIdname()
    panel_id = hex(id(LIGHTMETER_PT_main_panel))
    bpy.types.WindowManager.light_meter_panels = \
        bpy.props.CollectionProperty(type=LightMeterPanelState)
    bpy.types.Scene.light_meter = bpy.props.PointerProperty(type=LightMeterProperties)

def unregister():
    del bpy.types.WindowManager.light_meter_panels
    del bpy.types.Scene.light_meter
