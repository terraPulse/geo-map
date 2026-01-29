# Introduction

The map tile generation is a process that converts raster data into a set of map tiles that can be displayed on a web map. The map tiles are generated using a process called "tiling". The tiling process involves breaking the input data into smaller, manageable pieces called "tiles". Each tile is then converted into a map tile that can be displayed on a web map.

Three steps are invovled for the map tile generation process: 

1. Create map tile task
2. Enable dynamic map tiles
3. Pre-generate map tiles

# Create map tile task

A map tile layer can be created by the `build_tiles_make.py` script.

```
build_tiles_make.py -i/--input <input data> -r/--region <region file> -t/--tag <layer ID> --tile-merge <number of tiles to merge> --hillshade <true/false>
```

The key parameters are:

- **-i/--input:** the input file (e.g., a shapefile or a raster file)
- **-r/--region:** the region file (e.g., a shapefile), the data will be clipped to the region.
- **-t/--tag:** the layer ID
- **--tile-merge:** the number of tiles to merge
- **--hillshade:** whether to apply hillshade background

**For example:**

```
build_tiles_make.py -i s3://landsat-tcc-west-2/lincolninst/s2/water/comp02/y2025/list.shp -r s3://landsat-tcc-west-2/lincolninst/data/Lincoln_AOI.shp -t lincoln/water_freq/y2025 --tile-merge 8 -a mean --hillshade true -l 3 5
```

# Enable dynamic map tiles

This step enables the dynamic map tile generation, which will generate all map tiles for the selected levels.

```
enable_dynamic_levels.py -t/--tag <layer ID> -l/--levels <levels>
```

**For example:**

```
enable_dynamic_levels.py -t lincoln/water_freq/y2025 -l 3-12
```

Note: The interpolation levels should be selected based on the native resolution of the input data. For example, level 12 could be selected as the native resolution level for a 30-m resolution data. Details of zoom levels can be found at [[https://wiki.openstreetmap.org/wiki/Zoom_levels]].

# Pre-generate map tiles

Map tiles for the selected levels need to be generated for the selected zoom levels using command:

```
build_tiles_task.py -t/--tag <layer ID> -l/--levels <levels>
```

**For example:**

```
build_tiles_task.py -t lincoln/water_freq/y2025 -l 3-12
```

**Note:** 

1. It is important to ensure the complete generation of map tiles at these selected map tile levels.
2. Clean up pre-generated map tiles for other zoom levels if there are any. 
3. The command supports multiprocessing and AWS Batch.

