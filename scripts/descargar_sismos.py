import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

URL = 'https://earthquake.usgs.gov/fdsnws/event/1/query'
AGENTE = 'dashboard-sismos-peru/1.0'
CONTACTO = 'tu_correo@ejemplo.com'
HEADERS = {'User-Agent': AGENTE + ' (uso educativo; ' + CONTACTO + ')'}
CSV = Path('data/sismos_peru.csv')
LOG = Path('data/log_ejecuciones.csv')
A_LIMA = timedelta(hours=-5)
FMT = '%Y-%m-%d %H:%M:%S'


def rango(m):
    if m < 4:
        return 'A: 2,5 a 3,9'
    if m < 5:
        return 'B: 4,0 a 4,9'
    return 'C: 5,0 o más'


def descargar(dias):
    ahora = datetime.now(timezone.utc)
    inicio = (ahora - timedelta(days=dias)).strftime('%Y-%m-%d')
    params = dict(
        format='geojson',
        starttime=inicio,
        minmagnitude=2.5,
        orderby='time',
        limit=20000,
        minlatitude=-19,
        maxlatitude=1,
        minlongitude=-82,
        maxlongitude=-68,
    )
    for intento in range(1, 4):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=60)
            r.raise_for_status()
            datos = r.json()
            if datos.get('type') == 'FeatureCollection':
                return datos['features']
        except Exception as e:
            print('Intento', intento, 'falló:', e)
        time.sleep(10 * intento)
    raise RuntimeError('No se obtuvo una respuesta válida del USGS')


def transformar(features, ahora):
    filas = []
    for f in features:
        p = f['properties']
        g = f['geometry']['coordinates']
        lugar = p.get('place') or ''
        mag = p.get('mag')
        if 'peru' not in lugar.lower() or mag is None:
            continue
        ms = p['time'] / 1000
        t = datetime.fromtimestamp(ms, tz=timezone.utc).replace(tzinfo=None)
        lima = t + A_LIMA
        filas.append({
            'id': f['id'],
            'fecha_hora_utc': t.strftime(FMT),
            'fecha_hora_lima': lima.strftime(FMT),
            'fecha_lima': lima.strftime('%Y-%m-%d'),
            'magnitud': mag,
            'tipo_magnitud': p.get('magType'),
            'rango_magnitud': rango(mag),
            'lugar': lugar,
            'latitud': g[1],
            'longitud': g[0],
            'profundidad_km': g[2],
            'estado': p.get('status'),
            'tsunami': p.get('tsunami') or 0,
            'significancia': p.get('sig') or 0,
            'url': p.get('url'),
            'ingestado_utc': ahora.strftime(FMT),
            'ingestado_lima': (ahora + A_LIMA).strftime(FMT),
        })
    return pd.DataFrame(filas)


def main():
    existe = CSV.exists()
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    dias = 7 if existe else 365
    features = descargar(dias)
    nuevo = transformar(features, ahora)

    if not nuevo.empty:
        assert nuevo['magnitud'].between(0, 10).all()
        assert nuevo['latitud'].between(-19, 1).all()
    elif not existe:
        raise RuntimeError('La carga inicial no devolvió eventos')

    if existe:
        antiguo = pd.read_csv(CSV, dtype={'id': str})
        total = pd.concat([nuevo, antiguo], ignore_index=True)
    else:
        total = nuevo
    total = total.drop_duplicates('id', keep='first')
    total = total.sort_values('fecha_hora_utc', ascending=False)

    CSV.parent.mkdir(exist_ok=True)
    total.to_csv(CSV, index=False, encoding='utf-8')

    fila = pd.DataFrame([{
        'ejecutado_utc': ahora.strftime(FMT),
        'eventos_descargados': len(features),
        'eventos_peru': len(nuevo),
        'total_filas': len(total),
    }])
    fila.to_csv(LOG, mode='a', header=not LOG.exists(), index=False)
    print(fila.to_string(index=False))


if __name__ == '__main__':
    main()
