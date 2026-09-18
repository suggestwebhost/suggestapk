FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Buildozer and Android NDK system dependencies
RUN apt-get update && apt-get install -y \
    git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config \
    zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev \
    libssl-dev python3-setuptools python3-dev build-essential curl wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
RUN pip3 install --upgrade pip virtualenv cython buildozer celery flask

# Create a non-root user (Buildozer requirement)
RUN useradd -m builder
USER builder
WORKDIR /home/builder

# Pre-initialize buildozer to cache dependencies if needed
RUN buildozer --version

EXPOSE 5000
