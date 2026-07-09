import bpy
import numpy as np
import os
import sys
import tempfile
from math import *

RESOLUTION = 512
SAMPLE_COUNT = 16

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
    weights = weightsIrradiance(h, w, span)

    buf = np.empty(w*h*4, dtype=np.float32)
    img.pixels.foreach_get(buf)

    px = buf.reshape(h, w, 4)[:, :, :3]  # RGB

    num = np.einsum('ij,ijc->c', weights, px, dtype=np.float64)
    den = np.sum(weights, dtype=np.float64)

    CIE = np.array([0.2126, 0.7152, 0.0722])
    E_rgb = 683*pi * num/den*CIE

    return E_rgb

def tempImgPath():
    tmp_dir = os.environ.get('TEMPDIR')
    print('   TEMPDIR:', tmp_dir)
    tmp_dir = tmp_dir.replace('\\', '/')
    return f'{tmp_dir}/_measure_render'

def ensureCyclesSettings(scene):
    meter = scene.light_meter
    resolution = meter.resolution
    samples = meter.sample_count

    scene.camera = meter.lightmeter_cam
    scene.render.engine = 'CYCLES'
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.use_compositing = 1
    scene.render.film_transparent = 0
    scene.cycles.samples = samples
    scene.cycles.film_exposure = 1.0
    if hasattr(scene.cycles, 'use_denoising'):
        scene.cycles.use_denoising = 0
    if hasattr(scene.cycles, 'device'):
        scene.cycles.device = 'GPU'

def resetCompositor(scene):
    scene.use_nodes = 1
    tree = scene.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()
    render_node = nodes.new('CompositorNodeRLayers')
    composite_node = nodes.new('CompositorNodeComposite')
    links.new(render_node.outputs['Image'], composite_node.inputs['Image'])

def buildMeasurement(scene, img, is_cancelled=0):
    meter = scene.light_meter
    cam_obj = meter.lightmeter_cam
    cam_data = cam_obj.data

    lux = 0
    ev = 0
    E_rgb = 0
    if not is_cancelled and meter and cam_data:
        if img:
            E_rgb = measureIlluminance(img, cam_data)
            lux = sum(E_rgb)
            ES100_C = lux*100/meter.calibration_constant
            ev = log2(ES100_C) if ES100_C > 0 else -10

    return {
        'lux': lux,
        'ev': ev,
        'rgb': E_rgb,
    }

def reportResult(data):
    lux = data['lux']
    ev = data['ev']
    img_path = data['img_path']
    print(f'METER_RESULT:{lux};{ev};{img_path}', flush=True)

def reportError(reason):
    print(f'METER_ERROR={reason}', flush=True)

def onRenderWrite(scene, depsgraph):
    img_path = bpy.path.ensure_ext(scene.render.filepath, '.exr')
    img_path = os.path.abspath(img_path)
    print('LOADING', img_path, flush=True)
    if os.path.exists(img_path):
        img = bpy.data.images.load(img_path)
        data = buildMeasurement(scene, img)
        data['img_path'] = img_path
        reportResult(data)
    else:
        print('   NOT FOUND!', flush=True)
        reportError('render_missing')
    bpy.ops.wm.quit_blender()

def runMeasurement():
    addon_id = next(
        (name for name in bpy.context.preferences.addons.keys()
        if name.endswith('.fotographie')),
        None
    )
    if addon_id:
        bpy.ops.preferences.addon_enable(module=addon_id)
    else:
        print('ADDON NOT FOUND: Fotographie')

    scene = bpy.context.scene
    ensureCyclesSettings(scene)
    resetCompositor(scene)

    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.filepath = tempImgPath()
    path_img = bpy.path.ensure_ext(scene.render.filepath, '.exr')
    if os.path.exists(path_img):
        os.remove(path_img)
    bpy.app.handlers.render_write.append(onRenderWrite)

    print('START', flush=True)
    bpy.ops.render.render(write_still=1)

if __name__ == '__main__':
    runMeasurement()
