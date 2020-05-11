# -*- coding: utf-8 -*-

# * Copyright (c) 2009-2018. Authors: see NOTICE file.
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


from __future__ import print_function, unicode_literals, absolute_import, division
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import os
from shapely.geometry import shape, box, Polygon, MultiPolygon,Point
from shapely import wkt
from glob import glob
from tifffile import imread
from csbdeep.utils import Path, normalize
from csbdeep.io import save_tiff_imagej_compatible

from stardist import random_label_cmap, _draw_polygons, export_imagej_rois
from stardist.models import StarDist2D

from cytomine import cytomine, models, CytomineJob
from cytomine.models import Annotation, AnnotationTerm, AnnotationCollection, ImageInstanceCollection
from PIL import Image
import argparse
import json
import logging


__author__ = "Maree Raphael <raphael.maree@uliege.be>"

def main(argv):
    with CytomineJob.from_cli(argv) as conn:
        conn.job.update(status=Job.RUNNING, progress=0, status_comment="Initialization of the StarDist detection")
        base_path = "{}".format(os.getenv("HOME")) # Mandatory for Singularity
        working_path = os.path.join(base_path,str(conn.job.id))
        
        #Loading pre-trained Stardist model
        np.random.seed(17)
        lbl_cmap = random_label_cmap()
        #Stardist H&E model downloaded from https://github.com/mpicbg-csbd/stardist/issues/46
        #Stardist H&E model downloaded from https://drive.switch.ch/index.php/s/LTYaIud7w6lCyuI
        model = StarDist2D(None, name='2D_versatile_HE', basedir='/models/')   #use local model file in ~/models/2D_versatile_HE/


        #Dump ROI annotations from Cytomine server to local images
        roi_annotations = AnnotationCollection()
        roi_annotations.project = conn.parameters.cytomine_id_project
        roi_annotations.term = conn.parameters.cytomine_id_roi_term
        roi_annotations.image = conn.parameters.cytomine_id_image
        roi_annotations.showWKT = True
        roi_annotations.fetch()
        print(roi_annotations)
        for roi in roi_annotations:
            #Get Cytomine ROI coordinates for remapping to whole-slide
            #Cytomine cartesian coordinate system, (0,0) is bottom left corner
            print("----------------------------ROI------------------------------")
            roi_geometry = wkt.loads(roi.location)
            print("ROI Geometry from Shapely: {}".format(roi_geometry))
            print("ROI Bounds")
            print(roi_geometry.bounds)
            minx=roi_geometry.bounds[0]
            miny=roi_geometry.bounds[3]
            #Dump ROI image into local PNG file
            roi_path=os.path.join(working_path,str(roi_annotations.project)+'/'+str(roi_annotations.image)+'/'+str(roi.id))
            roi_png_filename=os.path.join(roi_path+'/'+str(roi.id)+'png')
            roi.dump(dest_pattern=roi_png_filename,mask=True,alpha=True)
            #roi.dump(dest_pattern=os.path.join(roi_path,"{id}.png"), mask=True, alpha=True)
            
            #Stardist works with TIFF images without alpha channel, flattening PNG alpha mask to TIFF RGB
            im=Image.open(roi_png_filename)
            bg = Image.new("RGB", im.size, (255,255,255))
            bg.paste(im,mask=im.split()[3])
            roi_tif_filename=os.path.join(roi_path+'/'+str(roi.id)+'.tif')
            bg.save(roi_tif_filename,quality=100)
            X_files = sorted(glob(roi_path+'*.tif'))
            X = list(map(imread,X_files))
            #print("X image dimension: %d, number of images: %d" %(X[0].ndim,len(X)))

            n_channel = 3 if X[0].ndim == 3 else X[0].shape[-1]
            axis_norm = (0,1)   # normalize channels independently  (0,1,2) normalize channels jointly
            if n_channel > 1:
                print("Normalizing image channels %s." % ('jointly' if axis_norm is None or 2 in axis_norm else 'independently'))

            #Going over images in directory (in our case: one ROI per directory)
            for x in range(0,len(X)):
                print("------------------- Processing ROI file %d: %s" %(x,roi_tif_filename))
                img = normalize(X[x], conn.parameters.stardist_norm_perc_low, conn.parameters.stardist_norm_perc_high, axis=axis_norm)
                #Stardist model prediction with thresholds
                labels, details = model.predict_instances(img,
                                                          prob_thresh=conn.parameters.stardist_prob_t,
                                                          nms_thresh=conn.parameters.stardist_nms_t)
                #Save label image locally for inspection
                #matplotlib.image.imsave(working_path+'/'+str(roi.id)+os.path.basename(roi_filename)+"_label_"+str(len(details['coord']))+".png", labels)
                print("Number of detected polygons: %d" %len(details['coord']))
                cytomine_annotations = AnnotationCollection()
                for pos,polygroup in enumerate(details['coord'],start=1):
                    #Converting to Shapely annotation
                    points = list()
                    for i in range(len(polygroup[0])):
                        #Cytomine cartesian coordinate system, (0,0) is bottom left corner
                        #Mapping Stardist polygon detection coordinates to Cytomine ROI in whole slide image
                        p = Point(minx+polygroup[1][i],miny-polygroup[0][i])
                        points.append(p)

                    annotation = Polygon(points)
                    #Send annotation to Cytomine server
                    #Add annotation one by one (one http request per annotation), with term. Slowish.
                    #cytomine_annotation = Annotation(location=annotation.wkt,
                    #                                 id_image=conn.parameters.cytomine_id_image,
                    #                                 id_project=conn.parameters.cytomine_id_project).save()
                    #Add term to annotation to Cytomine server
                    #AnnotationTerm(cytomine_annotation.id, conn.parameters.cytomine_id_cell_term).save()
                    print(".",end = '',flush=True)

                    #Alternative: Append to Annotation collection 
                    cytomine_annotations.append(Annotation(location=annotation.wkt,
                                                           id_image=conn.parameters.cytomine_id_image,
                                                           id_project=conn.parameters.cytomine_id_project,
                                                           id_terms=[conn.parameters.cytomine_id_cell_term]))
                    
                #Alternative (faster): add collection of annotations (without term) in one http request
                ca = cytomine_annotations.save()


                
if __name__ == "__main__":
    main(sys.argv[1:])
