FROM python:3.7-slim as python
FROM rocker/r-ver:3.6.3

# There is also the deadsnakes PPA for python installs, rather than apt-get install python3
COPY --from=python / /

# install R dependencies
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
	build-essential \
	wget \
	libboost-all-dev \
	libxml2-dev \
	libcurl4-openssl-dev \
	libssl-dev \
	fonts-open-sans \
	fonts-arkpandora \
	fonts-adf-verana \
	gnupg2

WORKDIR /opt

COPY . /opt

RUN pip3 install -r nb-etl-requirements.txt \
	&& Rscript install_packages.R


ENTRYPOINT ["bash", "/opt/nb-etl-run.sh"]
