
FROM minfeng/landsat-util:latest

RUN pip install pillow

LABEL creator Min Feng
ENV DEBIAN_FRONTEND noninteractive

WORKDIR /opt

ADD util /opt/lib
RUN cd /opt/lib && python setup.py install

RUN rm -rf /opt/lib
