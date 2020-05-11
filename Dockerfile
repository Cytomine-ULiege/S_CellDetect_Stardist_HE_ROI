FROM python:3.7-stretch

# -----------------------------------------------------------------------------
# Install Stardist and tensorflow
RUN pip install tensorflow==1.15
RUN pip install stardist
RUN mkdir -p /models && \
    cd /models && \
    mkdir -p 2D_versatile_HE
ADD config.json /models/2D_versatile_HE/config.json
ADD thresholds.json /models/2D_versatile_HE/thresholds.json
ADD weights_best.h5 /models/2D_versatile_HE/weights_best.h5
RUN chmod 444 /models/2D_versatile_HE/config.json
RUN chmod 444 /models/2D_versatile_HE/thresholds.json
RUN chmod 444 /models/2D_versatile_HE/weights_best.h5


# -----------------------------------------------------------------------------
# Install Cytomine python client
RUN git clone https://github.com/cytomine-uliege/Cytomine-python-client.git && \
    cd /Cytomine-python-client && git checkout tags/v2.5.1 && pip install . && \
    rm -r /Cytomine-python-client
# -----------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# Install scripts
ADD descriptor.json /app/descriptor.json
RUN mkdir -p /app
ADD run.py /app/run.py

ENTRYPOINT ["python3", "/app/run.py"]

