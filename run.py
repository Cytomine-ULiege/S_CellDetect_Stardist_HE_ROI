# -*- coding: utf-8 -*-

# * Copyright (c) 2009-2022. Authors: see NOTICE file.
# *
# * Licensed under the Apache License, Version 2.0 (the "License");
# * you may not use this file except in compliance with the License.
# * You may obtain a copy of the License at
# *
# *      http://www.apache.org/licenses/LICENSE-2.0
# *
# * Unless required by applicable law or agreed to in writing, software
# * distributed under the License is distributed on an "AS IS" BASIS,
# * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# * See the License for the specific language governing permissions and
# * limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import numpy as np
import sys
import os

from csbdeep.utils import normalize
from glob import glob
from PIL import Image
from shapely.geometry import Polygon, Point
from shapely import wkt
from tifffile import imread

from stardist.models import StarDist2D

from cytomine import CytomineJob
from cytomine.models import (
    Annotation, AnnotationCollection, ImageInstanceCollection, Job
)

__author__ = "Maree Raphael <raphael.maree@uliege.be>"


def main(argv):
    with CytomineJob.from_cli(argv) as conn:
        conn.job.update(status=Job.RUNNING, progress=0, statusComment="Initialization...")
        base_path = os.getenv("HOME")  # Mandatory for Singularity
        working_path = os.path.join(base_path, str(conn.job.id))

        # Loading pre-trained Stardist model
        np.random.seed(17)

        # use local model file in ~/models/2D_versatile_HE/
        model = StarDist2D(None, name='2D_versatile_HE', basedir='/models/')

        # Select images to process
        images = ImageInstanceCollection().fetch_with_filter(
            "project",
            conn.parameters.cytomine_id_project
        )

        if conn.parameters.cytomine_id_images == 'all':
            list_imgs = [int(image.id) for image in images]
        else:
            list_imgs = [int(id_img) for id_img in conn.parameters.cytomine_id_images.split(',')]

        # Go over images
        for id_image in conn.monitor(list_imgs, prefix="Running detection on image", period=0.1):
            # Dump ROI annotations in img from Cytomine server to local images
            roi_annotations = AnnotationCollection(
                project=conn.parameters.cytomine_id_project,
                term=conn.parameters.cytomine_id_roi_term,
                image=id_image,
                showWKT=True
            ).fetch()

            print(roi_annotations)

            # Go over ROI in this image
            for roi in roi_annotations:
                # Get Cytomine ROI coordinates for remapping to whole-slide
                # Cytomine cartesian coordinate system, (0,0) is bottom left corner
                print("----------------------------ROI------------------------------")
                roi_geometry = wkt.loads(roi.location)
                print(f"ROI Geometry from Shapely: {roi_geometry}")
                print("ROI Bounds")
                print(roi_geometry.bounds)

                minx, miny = roi_geometry.bounds[0], roi_geometry.bounds[3]

                # Dump ROI image into local PNG file
                roi_path = os.path.join(
                    working_path,
                    str(roi_annotations.project),
                    str(roi_annotations.image),
                    str(roi.id)
                )
                roi_png_filename = os.path.join(roi_path, f'{roi.id}.png')
                print(f"roi_png_filename: {roi_png_filename}")
                roi.dump(dest_pattern=roi_png_filename, mask=True, alpha=True)

                # Stardist works with TIFF images without alpha channel, flattening PNG alpha mask to TIFF RGB
                im = Image.open(roi_png_filename)
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[3])

                roi_tif_filename = os.path.join(roi_path, f'{roi.id}.tif')
                bg.save(roi_tif_filename, quality=100)

                X_files = sorted(glob(os.path.join(roi_path, f'{roi.id}*.tif')))
                X = list(map(imread, X_files))
                n_channel = 3 if X[0].ndim == 3 else X[0].shape[-1]
                axis_norm = (0, 1)  # normalize channels independently  (0,1,2) normalize channels jointly
                if n_channel > 1:
                    type = 'jointly' if axis_norm is None or 2 in axis_norm else 'independently'
                    print(f"Normalizing image channels {type}.")

                # Going over ROI images in ROI directory (in our case: one ROI per directory)
                for x in range(0, len(X)):
                    print(f"------------------- Processing ROI file {X}: {roi_tif_filename}")
                    img = normalize(
                        X[x],
                        conn.parameters.stardist_norm_perc_low,
                        conn.parameters.stardist_norm_perc_high,
                        axis=axis_norm
                    )
                    # Stardist model prediction with thresholds
                    labels, details = model.predict_instances(
                        img,
                        prob_thresh=conn.parameters.stardist_prob_t,
                        nms_thresh=conn.parameters.stardist_nms_t
                    )

                    print("Number of detected polygons: %d" % len(details['coord']))

                    cytomine_annotations = AnnotationCollection()
                    # Go over detections in this ROI, convert and upload to Cytomine
                    for polygroup in details['coord']:
                        # Converting to Shapely annotation
                        points = list()
                        for i in range(len(polygroup[0])):
                            # Cytomine cartesian coordinate system, (0,0) is bottom left corner
                            # Mapping Stardist polygon detection coordinates to Cytomine ROI in whole slide image
                            p = Point(minx + polygroup[1][i], miny - polygroup[0][i])
                            points.append(p)

                        annotation = Polygon(points)
                        # Append to Annotation collection
                        cytomine_annotations.append(
                            Annotation(
                                location=annotation.wkt,
                                id_image=id_image,  # conn.parameters.cytomine_id_image,
                                id_project=conn.parameters.cytomine_id_project,
                                id_terms=[conn.parameters.cytomine_id_cell_term]
                            )
                        )
                        print(".", end='', flush=True)
                    print()

                    # Send Annotation Collection (for this ROI) to Cytomine server in one http request
                    cytomine_annotations.save()

        conn.job.update(status=Job.TERMINATED, progress=100, statusComment="Finished.")


if __name__ == "__main__":
    main(sys.argv[1:])
