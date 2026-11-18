# Studying Redhead

### Unsupervised Planetary Anomaly Detection & 3D Mapping

## Overview

Studying Redhead is a geospatial digital twin project designed to process NASA Planetary Data System (PDS) datasets, specifically MOLA topography and CTX imagery.

The project aims to employ Variational Autoencoders (VAEs) for unsupervised planetary anomaly detection and visualize discovered anomalies using an interactive WebGL-based 3D terrain interface.

## Project Objectives

- Develop a memory-efficient planetary data ingestion pipeline.
- Perform geospatial alignment and radiometric preprocessing.
- Detect spatial anomalies using unsupervised deep learning.
- Render planetary terrain and anomaly heatmaps interactively.
- Establish a reproducible and scalable MLOps architecture.

## Directory Structure

- `configs/` — Centralized project configuration.
- `data/raw/` — Original, unmodified planetary datasets.
- `data/interim/` — Intermediate preprocessing outputs.
- `data/processed/` — Model-ready geospatial datasets.
- `src/pipeline/` — Core data engineering pipelines.
- `src/utils/` — Shared utility functions.
- `logs/` — Persistent execution logs.
- `notebooks/` — Exploratory spatial data analysis.

## Technology Stack

**Data Engineering:** Python, GDAL, Rasterio, GeoPandas, NumPy, SciPy.

**Machine Learning (Planned):** PyTorch, Variational Autoencoders.

**Backend (Planned):** FastAPI.

**Frontend (Planned):** React, WebGL.

**Deployment (Planned):** Docker, GitHub Actions.

## Earth Observation Transferability

The architecture is intended to be adaptable to terrestrial remote sensing datasets for applications including landslide detection, flood assessment, environmental degradation monitoring, and disaster risk analysis.

## Development Status

Phase 1 — Multi-Modal Data Engineering & Geospatial Alignment.

Currently under active development.