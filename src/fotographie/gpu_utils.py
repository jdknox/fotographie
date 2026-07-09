import bpy
import gpu
import time
import numpy as np

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

    b_type = 'UBYTE'
    ch = 4
    data = gpu.types.Buffer(b_type, w*h*ch)    
    fb.read_color(x, y, w, h, ch, 0, b_type, data=data)

    start = time.perf_counter()
    pos = findBlueRun(data, w, h)

    # if DEBUG:
    #     rgb = np.asarray(data, dtype=np.float32)/255
    #     if ch == 3:
    #         rgb = rgb.reshape(-1, 3)
    #         alpha = np.ones((rgb.shape[0], 1), dtype=rgb.dtype)
    #         rgba = np.hstack((rgb, alpha)).reshape(-1)
    #     else:
    #         rgba = rgb
    #     name = 'RegionCapture'
    #     img = I.get(name) or I.new(name=name, width=w, height=h)
    #     if list(img.size) != [w, h]:
    #         I.remove(img)
    #         img = I.new(name=name, width=w, height=h)
    #     img.pixels.foreach_set(rgba)
    elapsed = time.perf_counter() - start
    # log.debug(f'{pos=} (took {elapsed*1000:0.1f} ms)')
    return pos
