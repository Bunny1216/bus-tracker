#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
cd backend
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py seed_data                 # idempotent, but resets route/stops from data/ - remove after first deploy
python manage.py createsuperuser --noinput || true   # needs DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD