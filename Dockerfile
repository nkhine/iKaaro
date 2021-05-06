FROM nkhine/itools:latest

# Install ikaaro dependencies
RUN mkdir -p /tmp/ikaaro
ADD ./ /tmp/ikaaro/
RUN pip install -r /tmp/ikaaro/requirements.txt

# Install ikaaro
WORKDIR /tmp/ikaaro
RUN python setup.py install

# Workdir is /home/ikaaro
WORKDIR /home/ikaaro
RUN  icms-init.py --email=norman@khine.net ikaaro
EXPOSE 8080
CMD [ "icms-start.py", "--detach", "ikaaro" ]