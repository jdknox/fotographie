import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from . import logger as log


def ensureLightmeterHandler(tool, context):
    log.debug(f'Ensure lightmeter handler for {tool}')
    space_type = bpy.types.SpaceView3D
    if hasattr(space_type, 'lightmeter_handler'):
        removeLightmeterHandler()

    def drawLightmeter(tool, context):
        region = context.region
        if region is None:
            log.warning('Lightmeter draw handler missing region')
            return

        x0 = 20
        y0 = 40
        w = 200
        h = 80

        coords = [
            (x0,     y0),
            (x0+w,   y0),
            (x0+w,   y0+h),
            (x0,     y0+h),
        ]

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINE_LOOP', {'pos': coords})

        gpu.state.blend_set('ALPHA')
        shader.bind()
        shader.uniform_float('color', (1.0, 1.0, 0.0, 1.0))
        batch.draw(shader)
        gpu.state.blend_set('NONE')

    handler = bpy.types.SpaceView3D.draw_handler_add(
        drawLightmeter,
        (tool, context),
        'WINDOW',
        'POST_PIXEL'
    )
    space_type.lightmeter_handler = handler


def removeLightmeterHandler():
    space_type = bpy.types.SpaceView3D
    if hasattr(space_type, 'lightmeter_handler'):
        h = space_type.lightmeter_handler
        bpy.types.SpaceView3D.draw_handler_remove(h, 'WINDOW')
        delattr(space_type, 'lightmeter_handler')
    else:
        log.debug('Lightmeter handler missing on remove')


class LightmeterSettings(bpy.types.PropertyGroup):
    iso: bpy.props.IntProperty(name='ISO', default=100, min=50, max=12800)

class LightmeterTool(bpy.types.WorkSpaceTool):
    bl_idname = 'view3d.lightmeter_tool'
    bl_label = 'Light Meter'
    bl_description = 'Light meter overlay'
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_icon = 'ops.generic.select_circle'
    bl_widget = None

    @classmethod
    def setup(cls, context):
        log.debug('Lightmeter tool setup')
        ensureLightmeterHandler(cls, context)

    @classmethod
    def draw_settings(cls, context, layout, tool):
        props = context.scene.toolmeter_settings
        layout.prop(props, 'iso')


def register():
    # bpy.utils.register_class(LightmeterSettings)
    bpy.types.Scene.toolmeter_settings = bpy.props.PointerProperty(
        type=LightmeterSettings
    )

    bpy.utils.register_tool(
        LightmeterTool,
        after={'builtin.measure'},
        # separator=True,
        # group=True
    )


def unregister():
    removeLightmeterHandler()
    del bpy.types.Scene.toolmeter_settings
    bpy.utils.unregister_tool(LightmeterTool)
    # bpy.utils.unregister_class(LightmeterSettings)


if __name__ == '__main__':
#    unregister()
    register()
