# S_CellDetect_Stardist_ROI
Cytomine app for Cell (Nuclei) Detection in ROIs, using Stardist Python code (https://github.com/mpicbg-csbd/stardist/)
by Uwe Schmidt, Martin Weigert, Coleman Broaddus, and Gene Myers: Cell Detection with Star-convex Polygons. International Conference on Medical Image Computing and Computer-Assisted Intervention (MICCAI), Granada, Spain, September 2018.


This implementation applies a Stardist pre-trained model (versatile_HE) to Cytomine regions of interest within large whole-slide images. A Cytomine ROI annotation term identifier is given and the app applies the algorithm to all Cytomine ROI annotations labeled by the user, with this term, in whole images. Detected objects are labeled with object term identifier.

While the original model was trained with H&E images, it seems to produce decent results with other stainings. Future work will investigate benchmarking and fine-tuning models with specific data.

This version use tensorflow CPU version (See Dockerfile) to ensure compatibility with many computers.

Here is an example of StarDist detections in Cytomine web viewer of a whole-slide image:

![](screenshot.jpg)
![](screenshot-launch.jpg)
![](screenshot-detections.jpg)
