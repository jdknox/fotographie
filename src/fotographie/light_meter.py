#

import bpy
import blf

from bpy.props import *
from mathutils import *

import os
from dataclasses import dataclass as struct
from math import *

# from .main import generateApertures, generateShutterSpeeds, generateISOSpeeds, \
#     apertureFromExponent, \
#     CameraExposureSettings
from .camera import *
from . import background_job
from . import logger as log

DEBUG = 0
BL_CATEGORY = 'SuperMeter'
LIGHT_METER_TRACK_TO = 'Track To'
LIGHT_METER_CAM = '.LightMeterCamera'

LAYOUT_PADDING_PIXELS = {
    'LAYOUT_BOX': -1,
    'LAYOUT_COLUMN': 5,
    'LAYOUT_ROOT': 10,
    'LAYOUT_ROW': 0,
}

ENUM_STEP_SOURCES = {
    'shutter_preset': generateShutterSpeeds,
    'aperture_preset': generateApertures,
    'iso_preset': generateISOSpeeds,
}

@enum
class MeteredType:
    invalid: 0
    F: ...
    T: ...
    ISO: ...

@struct
class Metered:
    type: MeteredType
    ev_value: float
    snapped: float
    tenths: int
    prefix: str
    suffix: str

def getEnumIdentifiers(container, prop_name):
    fn = ENUM_STEP_SOURCES.get(prop_name)
    current = getattr(container, prop_name)
    items = []
    index = -1
    for i, item in enumerate(fn(container)):
        items.append(item[0])
        if item[0] == current:
            index = i

    return index, items
    # prop = container.bl_rna.properties.get(prop_name)
    # if not prop:
    #     return []
    # return [item.identifier for item in prop.enum_items]

# ===== Sekonic-style exposure helpers =====
def getShutterMilliseconds(meter):
    ms = getShutterSeconds(meter)*1024
    return ms

def getShutterSeconds(meter:'LightMeterProperties'):
    EV_t = float(meter.exposure_settings.shutter_preset)/MAX_STEPS
    s = pow(2, EV_t)
    return s

def apertureFromMeter(meter):
    exponent = meter.exposure_settings.aperture_preset
    return apertureFromExponent(exponent)

def formatShutter(t):
    if t < 1:
        denom = int(round(1/t))
        return f'{denom}'
    return f'{t:d}s'

def stepTenths(ev):
    return ev - floor(ev)
    # step = 2*log2(v)
    # full = int(step)
    # frac = round(10*(step - full))
    # return int(2**(full/2)), frac

def calcMeasuredFromEV(meter):
    # EV at current ISO, using: EV_S = log2(N^2/t) - log2(S/100)
    # N^2/t = ES_100/C = ES100_C
    # N_100 = sqrt(t*ES100_C)
    # EV = 2*EV_a - EV_t - EV_S
    ev = meter.ev_value
    exps: CameraExposureSettings = meter.exposure_settings
    comp_dir = 1 if exps.comp_dir else -1
    step_size = int(exps.step_size)
    suffix = ''
    prefix = ''

    ES100_C = 2**(ev - comp_dir*meter.ec)
    EV_S = evFromPreset(exps.iso_preset)
    if ev <= LOWEST_EV:
        return Metered(type=0, ev_value=ev,
                       snapped=0, tenths='-',
                       prefix=prefix, suffix=suffix)

    if meter.mode == 'T':
        # Inputs: T + ISO -> measure F
        EV_t = evFromPreset(exps.shutter_preset)
        ev_adj = ev - comp_dir*meter.ec
        EV_a = EV_t + ev_adj + EV_S
        EV_full = floor(EV_a*step_size)/step_size
        EV_frac = round(10*(EV_a - EV_full))
        prefix = 'f/'

        return Metered(type=MeteredType.F, ev_value=EV_a,
                       snapped=EV_full, tenths=EV_frac,
                       prefix=prefix, suffix=suffix)

    if meter.mode == 'F':
        # Inputs: F + ISO -> measure T
        EV_a = evFromPreset(exps.aperture_preset)
        ev_adj = ev - comp_dir*meter.ec
        EV_t = EV_a - ev_adj - EV_S

        EV_full = floor(EV_t*step_size)/step_size
        EV_frac = round(10*(EV_t - EV_full))
        sign = -1 if EV_t < 0 else 1
        x = EV_full
        if EV_t > 6:
            x -= log2(60)
        shutter = snapRenard(pow(2, sign*x))

        is_minutes = 1 if EV_t > 6 else 0
        is_seconds = (1 - is_minutes) if EV_t > 0 else 0
        if is_minutes:
            suffix += "'"
        elif is_seconds:
            suffix += '"'
        else:
            prefix = '1/'

        return Metered(type=MeteredType.T, ev_value=EV_t,
                       snapped=shutter, tenths=EV_frac,
                       prefix=prefix, suffix=suffix)

    # TF: Inputs: T + F -> measure ISO
    t = getShutterSeconds(meter)
    N = apertureFromMeter(meter)
    S_meas = 100.0*(N*N/t)/ES100_C
    S_meas = max(3, min(409600, S_meas))
    return ('ISO', f'{int(round(S_meas))}')

def ensureMeterCamera(context):
    scene = context.scene
    meter:LightMeterProperties = scene.light_meter

    # Create or get dome camera
    cam_name = LIGHT_METER_CAM
    if cam_name not in bpy.data.objects:
        cam_data = bpy.data.cameras.new(name=cam_name)
        cam_data.display_size = 0.0625
        cam_data.clip_end = 1000.0
        cam_data.clip_start = 0.01171875

        cam_obj = bpy.data.objects.new(name=cam_name, object_data=cam_data)

        # Track to active camera
        active_cam = scene.camera
        cns = cam_obj.constraints.new(type='TRACK_TO')
        cns.name = LIGHT_METER_TRACK_TO
        if active_cam:
            cns.target = active_cam
    else:
        cam_obj = bpy.data.objects[cam_name]

    if not cam_obj.users_scene:
        scene.collection.objects.link(cam_obj)
        cam_obj.location = scene.cursor.location
        cam_obj.rotation_euler = (pi/2, 0, 0)  # Point forward
    meter.lightmeter_cam = cam_obj
    for f in [updateAperture, updateShutter, updateISOSpeed]:
        f(meter.exposure_settings, context)

    cam_data = cam_obj.data
    cexps = cam_data.exposure_settings
    log.debug(f'Scene camera presets: {cexps.aperture_preset}, {cexps.shutter_preset}, {cexps.iso_preset}')
    cam_data.type = 'PANO'
    cam_data.panorama_type = 'EQUIRECTANGULAR'
    cam_data.latitude_min = -pi/2
    cam_data.latitude_max = pi/2
    half_a = meter.dome_fov/2
    cam_data.longitude_min = -half_a*pi/180
    cam_data.longitude_max = -cam_data.longitude_min

    return cam_obj

def startBackgroundMeasurement(context, panel):
    return background_job.startBackgroundMeasurement(
        context,
        panel,
        handleBackgroundLine,
        finalizeBackgroundMeasurement,
    )

TOTAL_LINES = 62
def handleBackgroundLine(line, job):
    scene = job['scene']
    meter = scene.light_meter
    total = TOTAL_LINES + meter.sample_count
    if line.startswith('Fra:'):
        if '| Sample' in line:
            tail = line.rsplit('| Sample', 1)[-1].strip()
            samples, total_samples = [float(x) for x in tail.split('/', 1)]
            job['samples'] = samples
    else:
        print(f'[LightMeter BG] {line}')
    done = job['progress_count'] + job['samples']
    job['last_line'] = line
    meter.background_progress = done/total
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()
    if line.startswith('METER_'):
        job['result_line'] = line
        return 1
    return 0

def finalizeBackgroundMeasurement(job):
    proc = job['process']
    panel = job['panel']
    scene = job['scene']
    meter = scene.light_meter
    stdout = proc.stdout
    if stdout and not stdout.closed:
        stdout.close()
    code = proc.wait()
    print(f'[LightMeter BG] exit {code}')

    temp_blend = job['temp_blend']
    if os.path.exists(temp_blend):
        os.remove(temp_blend)

    meter.background_pending = 0
    meter.background_progress = 0.0
    setPanelMeasuring(panel, 0)

    data_line = job.get('result_line', '')
    if not data_line:
        log.error('Background measurement missing result output')
        return

    payload = data_line.split(':', 1)[-1]
    parts = payload.split(';')
    if len(parts) < 3:
        log.error(f'Background measurement invalid output: {data_line}')
        return

    meter.illuminance = float(parts[0])
    meter.ev_value = float(parts[1])

    img_path = parts[2]
    IMG_NAME = '.last_meter_debug'
    old = bpy.data.images.get(IMG_NAME)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.load(img_path)
    img.name = IMG_NAME


# ============= OPERATORS =============
class LIGHTMETER_OT_step_enum(bpy.types.Operator):
    bl_idname = 'lightmeter.step_enum'
    bl_label = 'Adjust Enum'
    bl_options = {'INTERNAL'}

    group_attr: StringProperty(default='') # type: ignore
    prop_name: StringProperty(default='') # type: ignore
    direction: IntProperty(default=0) # type: ignore

    def execute(self, context):
        meter = context.scene.light_meter
        exps:CameraExposureSettings = meter.exposure_settings

        idx, identifiers = getEnumIdentifiers(exps, self.prop_name)
        # identifiers = generateApertures(exps)
        idx_cur = exps.get(self.prop_name)
        # if not identifiers:
        #     return {'CANCELLED'}

        if self.direction > 0 and idx_cur < len(identifiers) - 1:
            idx_cur += 1
        elif self.direction < 0 and idx_cur > 0:
            idx_cur -= 1
        else:
            return {'CANCELLED'}

        setattr(exps, self.prop_name, identifiers[idx_cur])
        return {'FINISHED'}

class LIGHTMETER_OT_apply_to_camera(bpy.types.Operator):
    bl_idname = 'lightmeter.apply_to_camera'
    bl_label = 'Apply Meter To Camera'
    bl_description = 'Set Camera exposure settings to match meter'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, 'camera', 0)

    def execute(self:bpy.types.Operator, context):
        scene = context.scene
        cam_obj = scene.camera
        if not cam_obj:
            self.report({'WARNING'}, 'No active camera')
            return {'CANCELLED'}

        meter = scene.light_meter
        if not meter:
            self.report({'WARNING'}, 'Light meter state missing')
            return {'CANCELLED'}

        src = meter.exposure_settings
        dst = cam_obj.data.exposure_settings
        attrs = [
            'step_size',
            'aperture_index', 'aperture_preset',
            'shutter_index', 'shutter_preset',
            'iso_index', 'iso_preset',
            'ev_adjustment', 'comp_dir',
        ]

        for attr in attrs:
            setattr(dst, attr, getattr(src, attr))

        measured = calcMeasuredFromEV(meter)
        if measured.ev_value <= LOWEST_EV:
            self.report({'WARNING'}, 'Meter EV value too low for camera')
            # return {'CANCELLED'}

        steps = int(meter.exposure_settings.step_size)
        M = MAX_STEPS//steps
        log.debug(f'Meter EV raw values: {measured.ev_value}, {measured.ev_value*steps}, {int(measured.ev_value*steps)}')

        ev_value = measured.ev_value
        if meter.mode == 'F':
            ev_value = clamp(ev_value, FASTEST_SHUTTER_EV, SLOWEST_SHUTTER_EV)
        elif meter.mode == 'T':
            ev_value = clamp(ev_value, LOWEST_APERTURE_EV, HIGHEST_APERTURE_EV)
        elif meter.mode == 'ISO':
            ev_value = clamp(ev_value, SLOWEST_ISOSPEED_EV, FASTEST_ISOSPEED_EV)

        preset = floor(ev_value*steps)*M
        log.debug(f'Exposure preset: {preset}')
        if meter.mode == 'F':
            dst.shutter_preset = f'{preset}'
            dst.shutter_index = preset
        elif meter.mode == 'T':
            dst.aperture_preset = f'{preset}'
            dst.aperture_index = preset

        ctx = Struct(scene=scene, camera=cam_obj.data)
        updateExposure(dst, ctx)
        if measured.ev_value != ev_value:
            self.report({'WARNING'}, 'Meter EV value outside realistic camera range!')
        else:
            self.report({'INFO'}, 'Meter settings applied to active camera')
        return {'FINISHED'}

def setSpaceContext(type):
    error = 0
    try:
        bpy.ops.wm.context_set_enum(data_path='space_data.context', value=type)
    except (RuntimeError, TypeError):
        error = 'CAMER DATA tab not found'
    return error

class LIGHTMETER_OT_focus_scene_camera(bpy.types.Operator):
    bl_idname = 'lightmeter.focus_scene_camera'
    bl_label = 'View Scene Camera'
    bl_description = 'Select the scene camera and show its data tab in the Properties editor'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        scene = context.scene
        cam_obj = scene.camera
        if not cam_obj:
            self.report({'WARNING'}, 'No scene camera')
            return {'CANCELLED'}

        view_layer = context.view_layer
        for obj in view_layer.objects:
            obj.select_set(obj == cam_obj)
        view_layer.objects.active = cam_obj

        for area in context.window.screen.areas:
            if area.type != 'PROPERTIES':
                continue
            space = area.spaces.active
            if space.type != 'PROPERTIES':
                continue
            region = None
            for reg in area.regions:
                if reg.type == 'WINDOW':
                    region = reg
                    break
            if not region:
                continue

            items = space.bl_rna.properties['context'].enum_items.keys()
            if 'DATA' in items and space.show_properties_data:
                with context.temp_override(window=context.window, area=area, region=region):
                    error = setSpaceContext('DATA')
                    if error:
                        self.report({'ERROR'}, 'Camera Data tab not found.')
                break
            else:
                log.warning(f'Properties space lacks DATA context (type={space.type}, options={items})')
                self.report({'WARNING'}, 'Could not switch to Camera Data tab. It might be hidden.')

        # print(space.type, items)
        return {'FINISHED'}

class LIGHTMETER_OT_ensure_helper(bpy.types.Operator):
    bl_idname = 'lightmeter.ensure_helper'
    bl_label = 'Create Meter Camera'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        cam = ensureMeterCamera(context)
        if cam:
            self.report({'INFO'}, 'Meter camera ready')
        else:
            self.report({'WARNING'}, 'Unable to create meter camera')
        return {'FINISHED'}

class LIGHTMETER_OT_select_meter(bpy.types.Operator):
    bl_idname = 'lightmeter.select_meter'
    bl_label = 'Select Meter Camera'
    bl_description = 'Select the hidden light meter camera in the 3D View'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, 'light_meter', 0)

    def execute(self, context):
        cam_obj = ensureMeterCamera(context)
        if not cam_obj:
            self.report({'WARNING'}, 'Meter camera missing')
            return {'CANCELLED'}

        cam_obj.hide_set(False)
        cam_obj.hide_viewport = False
        cam_obj.hide_render = False

        view_layer = context.view_layer
        for obj in view_layer.objects:
            obj.select_set(obj == cam_obj)
        view_layer.objects.active = cam_obj
        self.report({'INFO'}, 'Meter camera selected')
        return {'FINISHED'}

class LIGHTMETER_OT_measure(bpy.types.Operator):
    '''Measure incident light on meter'''
    bl_idname = 'lightmeter.measure'
    bl_label = 'Measure Light'
    bl_options = {'REGISTER', 'UNDO'}

    panel = 0

    def invoke(self, context, event):
        self.panel = LIGHTMETER_PT_main_panel
        setPanelMeasuring(self.panel)
        ensureMeterCamera(context)
        if startBackgroundMeasurement(context, self.panel):
            return {'FINISHED'}
        setPanelMeasuring(self.panel, 0)
        self.report({'ERROR'}, 'Unable to start measurement')
        return {'CANCELLED'}

def getCameraItems(meter:'LightMeterProperties', context):
    items = []
    target_cam_enum = meter.get('target_camera')
    constraint = getConstraint(meter)

    target = 0
    for obj in context.scene.objects:
        if (obj.type == 'CAMERA') and (obj != meter.lightmeter_cam):
            items.append((obj.name, obj.name, obj.data.name))
        elif constraint.target and constraint.target.name == obj.name:
            target = 'N/A'

    if not constraint.target:
        items.append(('NONE', '', ''))
    elif target == 'N/A':
        items.append(('N/A', 'Other', ''))

    return items if len(items) > 0 else [('NONE', 'No Cameras', '')]

def getConstraint(meter):
    cam_obj = meter.lightmeter_cam
    if not cam_obj: return 0
    constraint = cam_obj.constraints.get(LIGHT_METER_TRACK_TO)
    return constraint if constraint else 0

def updateTargetCamera_(meter, context):
    updateTargetCamera(meter, context)

def updateTargetCamera(meter:'LightMeterProperties', context, update_enum=0):
    constraint = getConstraint(meter)
    if not constraint: return

    if update_enum and meter.use_camera_list:
        target = constraint.target
        name = 'NONE'
        if target:
            if context.scene.objects[target.name].type == 'CAMERA':
                name = target.name
            else:
                name = 'N/A'

        meter.target_camera = name
    else:
        new_target = bpy.data.objects.get(meter.target_camera)
        if constraint and new_target:
            constraint.target = new_target

# ============= UI PANEL =============

class LIGHTMETER_PT_main_panel(bpy.types.Panel):
    '''Creates a Panel in the 3D viewport sidebar'''
    bl_label = 'Incident Light Meter'
    bl_idname = 'LIGHTMETER_PT_main_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = BL_CATEGORY
    bl_order = -1
    bl_hash = id(bl_idname)

    def draw_header(self, context):
        markPanelState(type(self), 0)
        layout = self.layout
        layout.label(text='', icon='LIGHT_HEMI')
        # layout.operator('lightmeter.measure', text='Measure', icon='SCENE')

    def draw(self, context):
        layout = self.layout
        meter:LightMeterProperties = context.scene.light_meter
        markPanelState(type(self), 1)

        # === Settings bar (T/F/ISO) ===
        set_box = layout.box()
        set_row = set_box.row(align=0)
        set_row.scale_y = 1.2
        lcol = set_row.column()
        lcol.prop(meter, 'mode', text='', icon='LIGHT_SUN', icon_only=1)
        lcol.operator('lightmeter.select_meter', text='', icon='LIGHT_HEMI')

        exps = meter.exposure_settings
        display_type = ''
        aux = ''
        ms = getShutterMilliseconds(meter)
        if meter.mode != 'F':
            c1 = set_row.column(align=True)
            c1.label(text='T')
            op = c1.operator('lightmeter.step_enum', text='', icon='TRIA_UP', emboss=0)
            op.group_attr = 'exposure_settings'
            op.prop_name = 'shutter_preset'
            op.direction = -1
            # c1.prop(exps, 'shutter_preset', text='')
            c1.prop_with_popover(exps, 'shutter_preset', text='',
                                 panel=LIGHTMETER_PT_aperture_menu.bl_idname)
            op = c1.operator('lightmeter.step_enum', text='', icon='TRIA_DOWN', emboss=0)
            op.group_attr = 'exposure_settings'
            op.prop_name = 'shutter_preset'
            op.direction = +1

            if ms >= 1000:
                suffix = ' s'
                str_ms = f'{ms/1024:0.0f}{suffix}'
            else:
                d = -floor(log10(ms)) + 2
                str_ms = f'{round(ms, d)} ms'
            if DEBUG: c1.box().label(text=f'{str_ms}')
        else:
            display_type = 'T'
            # set_row.box().label(text=f'{ms} ms')
            # if ms < 1000:
            #     aux = f'1/'

        if meter.mode != 'T':
            c1 = set_row.column(align=True)
            c1.label(text='F')
            op = c1.operator('lightmeter.step_enum', text='', icon='TRIA_UP', emboss=0)
            op.group_attr = 'exposure_settings'
            op.prop_name = 'aperture_preset'
            op.direction = -1
            c1.prop_with_popover(exps, 'aperture_preset', text='',
                                 panel=LIGHTMETER_PT_aperture_menu.bl_idname)
            op = c1.operator('lightmeter.step_enum', text='', icon='TRIA_DOWN', emboss=0)
            op.group_attr = 'exposure_settings'
            op.prop_name = 'aperture_preset'
            op.direction = +1
            if DEBUG: c1.box().label(text=f'{apertureFromMeter(meter):.2f}')
        else:
            display_type = 'F'
            aux=''

        if meter.mode != 'TF':
            c2 = set_row.column(align=True)
            c2.label(text='ISO')
            op = c2.operator('lightmeter.step_enum', text='', icon='TRIA_UP', emboss=False)
            op.group_attr = 'exposure_settings'
            op.prop_name = 'iso_preset'
            op.direction = -1
            c2.prop_with_popover(exps, 'iso_preset', text='',
                                 panel=LIGHTMETER_PT_iso_menu.bl_idname)
            op = c2.operator('lightmeter.step_enum', text='', icon='TRIA_DOWN', emboss=False)
            op.group_attr = 'exposure_settings'
            op.prop_name = 'iso_preset'
            op.direction = +1
            if DEBUG: c2.box().label(text=f'{exps.iso_preset}')
        else:
            display_type = 'ISO'

        create = layout.row()
        create.alignment = 'RIGHT'
        cam_obj = meter.lightmeter_cam
        if not (cam_obj and cam_obj.users_scene):
            create.operator('lightmeter.ensure_helper', text='Create Light Meter', icon='STRIP_COLOR_01')

        # === Big readout (measured value) ===
        disp = layout.split(factor=0.89)
        big = disp.box()
        big.alignment = 'EXPAND'
        inside = big.column()

        small = inside.split(factor=2/log2(context.region.width))
        r0 = small.row()
        r0.label(text=display_type, icon='NODE_SOCKET_STRING')
        if meter.background_pending:
            col = inside#.column()
            col.label(text='Background measurement running...', icon='TIME')
            col.progress(
                text='Metering...',
                factor=meter.background_progress,
                type='BAR', )
            big_height = 0.001
        else:
            big_height = 2.2

        info = r0.column(heading='h')
        info.alignment = 'RIGHT'
        info.scale_y = 1
        info.label(text='')
        info.label(text=aux)
        pad = info.row()
        pad.scale_y = big_height
        pad.label(text=display_type)

        # Your blf drawing code goes here
        measure = disp.row(align=1)
        state = getPanelState(LIGHTMETER_PT_main_panel)
        measuring = state.measuring or meter.background_pending
        measure.enabled = 0 if meter.background_pending else 1

        button = measure.column(align=1)
        button.alignment = 'EXPAND'
        button.scale_y = 4.85
        button.operator('lightmeter.measure',
                         text=' ', icon='THREE_DOTS', depress=measuring)

        # === Analog scale (-3 to +3 EV) ===
        analog_row = layout.box()
        analog_row.scale_y = 2
        analog_row.label()

        meter_cam = meter.lightmeter_cam or bpy.data.objects.get(LIGHT_METER_CAM)
        track = meter_cam.constraints.get(LIGHT_METER_TRACK_TO) if meter_cam else None

        cam_col = layout.box()
        cam_col.use_property_split = 1
        cam_col.use_property_decorate = 0

        button_row = cam_col.split(factor=0.4)#row(align=1)
        button_row.alignment = 'RIGHT'
        button_row.use_property_split = 1
        button_row.label(text='Send Exposure')
        camera_name = context.scene.camera.name if context.scene.camera else 0
        if camera_name:
            bb = button_row.box().split(factor=0.8)
            bb.operator('lightmeter.apply_to_camera',
                                text=camera_name, icon='FILE_ALIAS')
            bb.operator('lightmeter.focus_scene_camera',
                             icon='PROPERTIES', text='')
            panel = Struct(
                layout=cam_col,
                is_in_meter=1
            )
            CAMERA_PT_exposure_settings.draw(panel, context)

        else:
            button_row.alert = 1
            button_row.label(text='No Scene Camera!', icon='NOT_FOUND')

        cam_col.separator(type='LINE')
        target_row = cam_col.row(align=1)
        if track:
            if meter.use_camera_list:
                target_row.prop(meter, 'target_camera', icon='NONE', text='Aim at')
            else:
                target_row.prop(track, 'target', text='Aim at')  # shows search + eyedropper
            target_row.prop(meter, 'use_camera_list', text='', toggle=1, icon='CAMERA_DATA')
        else:
            cam_name = 'None! Light meter requires a tracking constraint.'
            target_row.label(text=f'Target: {cam_name}', icon='PIVOT_CURSOR')

        # Settings
        # settings_box = layout.box()
        state_names = {value: name for name, value in \
                            PANEL_STATE.__dict__.items()
                            if not name.startswith('_')}
        header, settings_box = layout.panel_prop(meter, 'show_settings')
        text = f'Settings: ({meter.illuminance:0.1f} lx; {meter.ev_value:0.3f})'
        # text += f' (panel_state:{state_names[meter.panel_state]})'
        header.label(text=text, icon='PREFERENCES')

        if not meter.show_settings:
            return

        settings_col = settings_box.column(align=1)
        settings_col.use_property_split = 1
        settings_col.use_property_decorate = 0

        comp = settings_col.split(align=1, factor=0.41)
        comp.use_property_split = 0
        comp_text = 'Additive' if exps.comp_dir else 'Subtractive'
        comp_icon = 'ADD' if exps.comp_dir else 'REMOVE'
        comp.prop(exps, 'comp_dir', text=comp_text, icon=comp_icon)
        comp.prop(meter, 'ec', text='EC')

        settings_col.prop(exps, 'step_size')
        settings_col.prop(meter, 'tenth_steps')

        settings_col.separator()
        settings_col.prop(meter, 'calibration_constant', expand=1)
        settings_col.prop(meter, 'dome_fov')
        settings_col.prop(meter, 'resolution')
        settings_col.prop(meter, 'sample_count')
        # settings_col.prop(meter, 'show_rgb')


# ============= PROPERTIES =============
class LightMeterProperties(bpy.types.PropertyGroup):
    illuminance: FloatProperty(
        name='Illuminance',
        description='Measured illuminance in lux',
        default=0.0,
        min=0.0,
        precision=1
    ) # type: ignore

    illuminance_rgb: FloatVectorProperty(default=[0.0]*3) # type: ignore

    ev_value: FloatProperty(
        name='EV',
        description='Exposure Value at current ISO',
        default=-10.0,
        precision=1
    ) # type: ignore

    calibration_constant: FloatProperty(
        name='Calibration Constant',
        description='Meter calibration constant (340 for lumisphere, 250 for flat, 12.5 for reflected)',
        default=340,
        min=10,
        max=500
    ) # type: ignore

    dome_fov: FloatProperty(
        name='Lumisphere FOV',
        description='Meter lumisphere dome angle of view (typically 180°-220°)',
        default=220,
        min=1,
        max=360
    ) # type: ignore

    resolution: IntProperty(
        name='Resolution',
        description='Measurement resolution (higher = more accurate)',
        default=512,
        min=128,
        max=8192
    ) # type: ignore

    sample_count: IntProperty(
        name='Samples',
        description='Render samples for measurement',
        default=8,
        min=1,
        max=4096
    ) # type: ignore

    show_rgb: BoolProperty(
        name='Show RGB',
        description='Display RGB channel breakdown',
        default=False
    ) # type: ignore

    background_pending: BoolProperty(
        name='Background Measurement Pending',
        default=False,
        options={'HIDDEN'}
    ) # type: ignore

    background_progress: FloatProperty(
        name='Background Progress',
        default=0.0,
        min=0.0,
        max=1.0,
        options={'HIDDEN'}
    ) # type: ignore

    show_settings: BoolProperty(name='Settings', default=False) # type: ignore

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
    ) # type: ignore

    exposure_settings: PointerProperty(type=CameraExposureSettings) # type: ignore

    ec: FloatProperty(
        name='Exposure Compensation',
        description='EC adjustment in stops',
        min=-5.0, max=5.0,
        default=0.0,
        precision=1,
        step=100/10,  # 1/10 stop increments
    ) # type: ignore

    tenth_steps: BoolProperty(
        name='Show 1/10 Steps',
        default=True
    ) # type: ignore

    target_camera: EnumProperty(
        name='Target Camera',
        items=getCameraItems,
        update=updateTargetCamera_
    ) # type:ignore
    lightmeter_cam: PointerProperty(type=bpy.types.Object) # type:ignore

    use_camera_list: BoolProperty(
        name='Filter Cameras Only',
        update=lambda meter, context: updateTargetCamera(meter, context, 1),
    ) # type:ignore

class LightMeterPanelState(bpy.types.PropertyGroup):
    panel_category: StringProperty(default='') #type:ignore
    is_open: BoolProperty(default=False) #type:ignore
    measuring: BoolProperty(default=False) #type:ignore

def _defer(idname, meter, prop, val):
    bpy.app.timers.register(lambda: setattr(meter, prop, val))
    # if meter.panel_owner == idname:
    #     bpy.app.timers.register(lambda: setattr(meter, prop, val))
    # else:
    #     bpy.app.timers.register(lambda: setattr(meter, 'panel_owner', idname))

class LIGHTMETER_PT_aperture_menu(bpy.types.Panel):
    bl_label = 'Select'
    bl_idname = 'LIGHTMETER_PT_SelectMenu'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'INSTANCED'}
    bl_category = BL_CATEGORY
    bl_ui_units_x = 10
    type = 'F_OR_T_MENU'
    light_meter_panel_states[bl_idname] = 0

    @classmethod
    def poll(cls, context):
        return panelPoll(cls, context)

    def draw(self, context):
        panelDraw(self, context)

def panelPoll(cls, context):
    meter:LightMeterProperties = context.scene.light_meter
    exps = meter.exposure_settings
    if light_meter_panel_states[cls.bl_idname] == PANEL_STATE.open:
        light_meter_panel_states[cls.bl_idname] = PANEL_STATE.closed
    return 1

def panelDraw(self, context):
    layout = self.layout
    meter:LightMeterProperties = context.scene.light_meter
    exps = meter.exposure_settings
    layout.ui_units_x = 6*int(exps.step_size)
    menu_type = getattr(self, 'type', 0)

    if light_meter_panel_states[self.bl_idname] == PANEL_STATE.closing:
        light_meter_panel_states[self.bl_idname] = PANEL_STATE.closed
        log.debug(f'Closing popup menu {menu_type}')
        return
    light_meter_panel_states[self.bl_idname] = PANEL_STATE.open
    # if meter.panel_state == PANEL_STATE.closing:
    #     defer(self.bl_idname, meter, 'panel_state', PANEL_STATE.closed)
    #     return
    # defer(self.bl_idname, meter, 'panel_state', PANEL_STATE.open)

    # cols = int(exps.step_size)
    if meter.mode == 'T':
        priority = 'shutter_preset'
        all = generateShutterSpeeds(exps)
    elif meter.mode == 'F':
        priority = 'aperture_preset'
        all = generateApertures(exps)

    if self.type == 'ISO_MENU':
        priority = 'iso_preset'
        all = generateISOSpeeds(exps)
    # if cols > 1:
    #     pad = -len(all) % cols
    #     all = np.array(all + [None]*pad, dtype=object)
    #     all = all.reshape(-1, cols).T.flatten()

    col = layout.column() #(columns=1, align=0, row_major=1)
    col.alignment = 'LEFT'
    i = 0
    for a in all[1:]:
        if not a:
            col.label()
            continue
        icon = 'LAYER_USED' if (int(a[0])%6) else 'DOT'
        if icon == 'DOT':
            row = col.row(align=1)
            i += 1
        # row.alignment='LEFT'
        # if(menu_type=='ISO_MENU'):
        #     print(f'row.prop_enum({exps}, {priority}, value={a[0]}, icon={icon})')
        row.prop_enum(exps, priority, value=a[0], text=a[1], icon=icon)

    # col.template_popup_confirm('lightmeter.aperture_popup', text='')

class LIGHTMETER_PT_iso_menu(bpy.types.Panel):
    bl_label = 'Select'
    bl_idname = 'LIGHTMETER_PT_ISOSelectMenu'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'INSTANCED'}
    bl_category = BL_CATEGORY
    type = 'ISO_MENU'
    light_meter_panel_states[bl_idname] = 0

    @classmethod
    def poll(cls, context):
        panelPoll(cls, context)

    def draw(self, context):
        panelDraw(self, context)

# ============= REGISTRATION =============

classes = [
    LightMeterPanelState,
    LightMeterProperties,
    LIGHTMETER_OT_ensure_helper,
    LIGHTMETER_OT_select_meter,
    LIGHTMETER_OT_measure,
    LIGHTMETER_OT_apply_to_camera,
    LIGHTMETER_OT_step_enum,
    LIGHTMETER_PT_main_panel,
]

def confirmPanel(panel, current_category):
    wm = bpy.context.window_manager
    state = getPanelState(panel)
    if state and state.is_open:
        if current_category == state.panel_category:
            return state
        else:
            return 0
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

bl_handlers = bpy.app.handlers
def register():
    bpy.types.WindowManager.light_meter_panels = \
        bpy.props.CollectionProperty(type=LightMeterPanelState)
    bpy.types.Scene.light_meter = bpy.props.PointerProperty(type=LightMeterProperties)

def unregister():
    del bpy.types.WindowManager.light_meter_panels
    del bpy.types.Scene.light_meter
