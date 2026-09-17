import numpy as np
import rasterio
from rasterio.transform import from_origin

a = np.zeros((8,8), np.uint8)
f = rasterio.MemoryFile()
d = f.open(driver='GTiff', height=8, width=8, count=1, dtype='uint8',
           transform=from_origin(30.5, 50.45, 0.001, 0.001), crs='EPSG:4326')
d.write(a, 1)
d.close()
b = f.getvalue()
r = rasterio.MemoryFile(b).open()
print('ROUNDTRIP_OK', r.read(1).shape, r.crs)
r.close()
