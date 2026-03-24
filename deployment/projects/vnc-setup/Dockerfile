FROM msjpq/kde-vnc:focal

RUN apt update

RUN apt install -y gpredict
RUN apt install -y telnet
RUN apt install -y ubuntu-standard
RUN apt install -y git

RUN apt install -y python3-pyqt5 python3-pip qttools5-dev-tools pyqt5-dev-tools
RUN echo "test"
WORKDIR /root
RUN git clone https://gitlab.com/carlgonz/suchai-commander.git SerialCommander
WORKDIR /root/SerialCommander
RUN make python3
RUN mkdir -p /root/.config/serialcommander
RUN cp config/* /root/.config/serialcommander
RUN python3 -m pip install pyserial
RUN python3 -m pip install pyzmq

RUN printf "kEmju7vu\nkEmju7vu\n\n" | vncpasswd /etc/vncpasswd

RUN sed -i 's/-SecurityTypes none/-rfbauth \/etc\/vncpasswd/g' /etc/services.d/tigervnc/run
RUN usermod -s /bin/bash root

RUN cp /etc/skel/.bashrc /root/.bashrc
ADD https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle /root/active.tle
RUN sed -i 's/ORBCOMM FM109/SUCHAI-2/g' /root/active.tle
