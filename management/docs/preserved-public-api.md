# Preserved public tile API

This branch does not change `serv/`, `util/`, or `lambda/handler.py`.

The current service still accepts:

- `/map/{tag}/{z}/{x}/{y}.png`, including tags that contain slashes
- `/zx_y/…`, `/zxy/…`, and `/xyz/{tag}/{x}/{y}/{z}.png` as described by the performance branch
- `/_query/loc`, `/_query/reg`, `/_query/cat`, `/_pixel`, `/_ndvi`, and the other `_` operations

Version 2 PNGs remain `{map_path}/{tag}/tiles/{z}/{x}/{y}.png`. Older layers omit `tiles/`. `setting.ini` remains the tile server's metadata file. Changing the new registry does not rewrite it and does not rebuild the pyramid.
