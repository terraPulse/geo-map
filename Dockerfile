
FROM minfeng/landsat-util:latest

RUN pip install pillow

LABEL creator Min Feng
ENV DEBIAN_FRONTEND noninteractive

WORKDIR /opt

ADD util /opt/lib
RUN pip install /opt/lib

RUN rm -rf /opt/lib
