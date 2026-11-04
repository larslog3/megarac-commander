FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN dpkg --add-architecture i386 && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    ipmitool \
    curl \
    ca-certificates \
    openjdk-8-jdk \
    icedtea-netx \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    fluxbox \
    xterm \
    xdotool \
    libc6:i386 \
    libstdc++6:i386 \
    libxext6:i386 \
    libxrender1:i386 \
    libxtst6:i386 \
    libxi6:i386 \
    && rm -rf /var/lib/apt/lists/* \
    && find /etc/ -name "java.security" -exec sed -i 's/^jdk.jar.disabledAlgorithms=.*/jdk.jar.disabledAlgorithms=/g' {} + \
    && find /etc/ -name "java.security" -exec sed -i 's/^jdk.tls.disabledAlgorithms=.*/jdk.tls.disabledAlgorithms=/g' {} +

# Create a borderless, chromeless noVNC viewer page (/usr/share/novnc/vnc_clean.html)
RUN cp /usr/share/novnc/vnc_lite.html /usr/share/novnc/vnc_clean.html && \
    sed -i 's/<head>/<head><style>#top_bar{display:none!important;}body,html{margin:0!important;padding:0!important;background:#000!important;overflow:hidden!important;}</style>/' /usr/share/novnc/vnc_clean.html

WORKDIR /app
COPY ModernJViewerBridge.java /app/ModernJViewerBridge.java
RUN javac -source 1.8 -target 1.8 /app/ModernJViewerBridge.java

COPY index.html /app/index.html
COPY bridge_server.py /app/bridge_server.py

EXPOSE 8765 6080
CMD ["python3", "/app/bridge_server.py", "--bind", "0.0.0.0", "--port", "8765"]
