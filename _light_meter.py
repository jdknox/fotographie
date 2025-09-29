#

import bpy
import numpy as np
from mathutils import *
from math import *
from bpy.props import *
from .main import F_STOPS, SHUTTER_VALUES

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

# ============= OPERATOR =============

class LIGHTMETER_OT_measure(bpy.types.Operator):
    '''Measure incident light at 3D cursor position'''
    bl_idname = 'lightmeter.measure'
    bl_label = 'Measure Light'
    bl_options = {'REGISTER', 'UNDO'}
    
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
                ESC = E*meter.iso/meter.calibration_constant
                meter.ev_value = log2(ESC) if ESC > 0 else -10

                # Calculate measured values based on priority mode
                if meter.ev_value > -10:
                    ev = meter.ev_value

                    if meter.priority_mode == 'T_PRIORITY':
                        # T Priority: Calculate F-stop from shutter and ISO
                        meter.measured_f_stop = sqrt(2**ev * meter.shutter_speed)
                        meter.measured_f_stop_fraction = round(10*log2(meter.measured_f_stop))

                    elif meter.priority_mode == 'F_PRIORITY':
                        # F Priority: Calculate shutter from F-stop and ISO
                        meter.measured_shutter = meter.f_stop**2 / 2**ev
                        meter.measured_shutter_fraction = 2  # Subscript indicator

                    elif meter.priority_mode == 'TF_PRIORITY':
                        # TF Priority: Calculate ISO from shutter and F-stop
                        needed_ev = log2(meter.f_stop**2 / meter.shutter_speed)
                        meter.measured_iso = int(meter.calibration_constant * E / 2**needed_ev)

        finally:
            bpy.data.scenes.remove(temp_scene)

        return {'FINISHED'}

# ============= UI PANEL =============

class LIGHTMETER_PT_main_panel(bpy.types.Panel):
    '''Creates a Panel in the 3D viewport sidebar'''
    bl_label = 'Incident Light Meter'
    bl_idname = 'LIGHTMETER_PT_main_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Light Meter'
    def draw_meter_display(self, layout, meter):
        '''Draw the main meter display similar to Sekonic'''
        
        # Black background box for meter display
        main_box = layout.box()
        main_box.scale_y = 1.5
        
        # Mode indicator at top
        mode_row = main_box.row()
        mode_row.scale_y = 0.8
        
        mode_icons = {
            'T_PRIORITY': 'RESTRICT_RENDER_OFF',
            'F_PRIORITY': 'CAMERA_DATA',
            'TF_PRIORITY': 'VIEW_CAMERA'
        }
        mode_labels = {
            'T_PRIORITY': 'T Priority Mode',
            'F_PRIORITY': 'F Priority Mode',
            'TF_PRIORITY': 'TF Priority Mode'
        }
        
        mode_row.label(text=mode_labels[meter.priority_mode],
                      icon=mode_icons[meter.priority_mode])
        
        # Setting values section
        settings_box = main_box.box()
        settings_row = settings_box.row(align=True)
        
        if meter.priority_mode == 'T_PRIORITY':
            # T Priority: Set shutter and ISO, measure f-stop
            col1 = settings_row.column()
            col1.label(text='T')
            col1.label(text=f'{self.format_shutter(meter.shutter_speed)}')
            
            col2 = settings_row.column()
            col2.label(text='ISO')
            col2.label(text=f'{meter.iso}')
            
        elif meter.priority_mode == 'F_PRIORITY':
            # F Priority: Set f-stop and ISO, measure shutter
            col1 = settings_row.column()
            col1.label(text='F')
            col1.label(text=f'{meter.f_stop:.1f}')
            
            col2 = settings_row.column()
            col2.label(text='ISO')
            col2.label(text=f'{meter.iso}')
            
        elif meter.priority_mode == 'TF_PRIORITY':
            # TF Priority: Set shutter and f-stop, measure ISO
            col1 = settings_row.column()
            col1.label(text='T')
            col1.label(text=f'{self.format_shutter(meter.shutter_speed)}')
            
            col2 = settings_row.column()
            col2.label(text='F')
            col2.label(text=f'{meter.f_stop:.1f}')
        
        # Measured value display (large)
        measured_box = main_box.box()
        measured_col = measured_box.column()
        measured_col.scale_y = 2.0
        
        if meter.ev_value > -10:
            if meter.priority_mode == 'T_PRIORITY':
                # Display measured f-stop
                measured_col.label(text=f'F  {meter.measured_f_stop:.1f}')
                if meter.measured_f_stop_fraction > 0:
                    sub_row = measured_col.row()
                    sub_row.scale_y = 0.5
                    sub_row.label(text=f'    {int(meter.measured_f_stop_fraction)}')
                    
            elif meter.priority_mode == 'F_PRIORITY':
                # Display measured shutter
                measured_col.label(text=f'T  {self.format_shutter(meter.measured_shutter)}')
                if meter.measured_shutter_fraction > 0:
                    sub_row = measured_col.row()
                    sub_row.scale_y = 0.5
                    sub_row.label(text=f'    {int(meter.measured_shutter_fraction)}')
                    
            elif meter.priority_mode == 'TF_PRIORITY':
                # Display measured ISO
                measured_col.label(text=f'ISO  {meter.measured_iso}')
        else:
            measured_col.label(text='---')
        
        # EV scale at bottom
        scale_row = main_box.row()
        scale_row.scale_y = 0.6
        scale_row.alignment = 'CENTER'
        
        # Draw scale markings
        if meter.ev_value > -10:
            ev_int = int(meter.ev_value)
            scale_text = ''
            for i in range(-2, 4):
                if i == 0:
                    scale_text += f'[{ev_int}] '
                else:
                    scale_text += f'{ev_int + i} '
            scale_row.label(text=scale_text)
        
        # Lux display
        info_row = main_box.row()
        info_row.label(text=f'{meter.illuminance:.0f} lux' if meter.illuminance > 0 else '--- lux')
        info_row.label(text=f'EV {meter.ev_value:.1f}' if meter.ev_value > -10 else '---')
    
    def format_shutter(self, shutter):
        '''Format shutter speed for display'''
        if shutter < 1:
            return f'1/{int(1/shutter)}' if shutter > 0 else '---'
        else:
            return f'{shutter:.1f}″'

    def draw(self, context):
        layout = self.layout
        meter = context.scene.light_meter
        
        # Main meter display
        self.draw_meter_display(layout, meter)
        
        # Measure button
        row = layout.row()
        row.scale_y = 2.0
        row.operator('lightmeter.measure', text='MEASURE', icon='LIGHT_SUN')

class LIGHTMETER_PT_settings_panel(bpy.types.Panel):
    '''Light Meter Settings'''
    bl_label = 'Settings'
    bl_idname = 'LIGHTMETER_PT_settings'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Light Meter'
    bl_parent_id = 'LIGHTMETER_PT_main_panel'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        meter = context.scene.light_meter
        
        col = layout.column(align=True)
        
        # Priority Mode
        col.label(text='Priority Mode:')
        col.prop(meter, 'priority_mode', text='')
        
        col.separator()
        
        # Input values based on mode
        if meter.priority_mode == 'T_PRIORITY':
            col.label(text='Settings:')
            col.prop(meter, 'shutter_speed')
            col.prop(meter, 'iso')
            
        elif meter.priority_mode == 'F_PRIORITY':
            col.label(text='Settings:')
            col.prop(meter, 'f_stop')
            col.prop(meter, 'iso')
            
        elif meter.priority_mode == 'TF_PRIORITY':
            col.label(text='Settings:')
            col.prop(meter, 'shutter_speed')
            col.prop(meter, 'f_stop')
        
        col.separator()
        
        # Advanced settings
        col.label(text='Advanced:')
        col.prop(meter, 'calibration_constant')
        col.prop(meter, 'step_increments')
        col.prop(meter, 'compensation_mode')
        
        col.separator()
        
        # Render settings
        col.label(text='Quality:')
        col.prop(meter, 'resolution')
        col.prop(meter, 'sample_count')

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

    # Priority mode
    priority_mode: EnumProperty(
        name='Priority Mode',
        description='Measurement priority mode',
        items=[
            ('T_PRIORITY', 'T Priority', 'Shutter priority - set shutter speed, measure aperture'),
            ('F_PRIORITY', 'F Priority', 'Aperture priority - set aperture, measure shutter'),
            ('TF_PRIORITY', 'TF Priority', 'Manual - set both, measure ISO'),
        ],
        default='T_PRIORITY'
    )
    
    # Input settings
    shutter_speed: FloatProperty(
        name='Shutter Speed',
        description='Shutter speed in seconds',
        default=0.008,  # 1/125
        min=0.0001,  # 1/10000
        max=30.0,
        precision=4
    )
    
    f_stop: FloatProperty(
        name='F-Stop',
        description='Aperture f-number',
        default=5.6,
        min=0.7,
        max=64.0,
        precision=1
    )

    ev_value: FloatProperty(
        name='EV',
        description='Exposure Value at current ISO',
        default=-10.0,
        precision=1
    )
    
    iso: IntProperty(
        name='ISO',
        description='Film speed/sensor sensitivity',
        default=100,
        min=25,
        max=25600
    )
    
    # Measured values
    measured_shutter: FloatProperty(default=0.0)
    measured_shutter_fraction: IntProperty(default=0)
    measured_f_stop: FloatProperty(default=0.0)
    measured_f_stop_fraction: IntProperty(default=0)
    measured_iso: IntProperty(default=0)
    
    calibration_constant: FloatProperty(
        name='Cal. Constant',
        description='Meter calibration constant (typically 250-340)',
        default=250,
        min=100,
        max=500
    )
    
    step_increments: EnumProperty(
        name='Step Increments',
        items=[
            ('1', '1 Step', 'Full stop increments'),
            ('1/2', '1/2 Step', 'Half stop increments'),
            ('1/3', '1/3 Step', 'Third stop increments'),
            ('1/10', '1/10 Step', 'Tenth stop increments'),
        ],
        default='1/3'
    )
    
    compensation_mode: EnumProperty(
        name='Compensation',
        items=[
            ('ADD', 'Additive', 'Add compensation'),
            ('SUB', 'Subtractive', 'Subtract compensation'),
        ],
        default='ADD'
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

# ============= REGISTRATION =============

# classes = [
#     LightMeterProperties,
#     LIGHTMETER_OT_measure,
#     LIGHTMETER_PT_main_panel,
# ]

def register():    
    bpy.types.Scene.light_meter = bpy.props.PointerProperty(type=LightMeterProperties)

def unregister():    
    del bpy.types.Scene.light_meter
