# Spotify Dashboard

Dashboard desarrollado en Python y Streamlit para analizar playlists de Spotify, visualizar estadísticas musicales y generar recomendaciones de artistas y canciones.

## Funcionalidades

- Autenticación con Spotify mediante OAuth.
- Selección y análisis de playlists propias.
- Cantidad total de canciones.
- Duración total de la playlist.
- Ranking de artistas más escuchados.
- Ranking de álbumes.
- Distribución de canciones por década.
- Cantidad de artistas y álbumes diferentes.
- Visualizaciones interactivas con Plotly.
- Recomendaciones de artistas mediante Last.fm.
- Sistema de afinidad basado en los artistas predominantes de la playlist.
- Portadas e información de artistas recomendados obtenidas desde Spotify.
- Creación automática de una playlist de descubrimientos.
- Validación de artistas para evitar agregar canciones incorrectas.
- Caché de consultas para reducir solicitudes a las APIs.
- Manejo de límites de solicitudes de Spotify.

## Tecnologías utilizadas

- Python
- Streamlit
- Spotipy
- Spotify Web API
- Last.fm API
- Pandas
- Plotly
- Requests
- python-dotenv

## Instalación

Clonar el repositorio:

```bash
git clone https://github.com/Alejo-AS/spotify-dashboard.git
```

Entrar a la carpeta del proyecto:

```bash
cd spotify-dashboard
```

Instalar las dependencias:

```bash
pip install -r requirements.txt
```

## Variables de entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
CLIENT_ID=tu_spotify_client_id
CLIENT_SECRET=tu_spotify_client_secret
LASTFM_API_KEY=tu_lastfm_api_key
```

El archivo `.env` contiene credenciales privadas y no debe subirse al repositorio.

## Configuración de Spotify

Para utilizar el dashboard es necesario crear una aplicación en Spotify for Developers y configurar la siguiente Redirect URI:

```text
http://127.0.0.1:8888/callback
```

El proyecto utiliza OAuth para acceder a la cuenta de Spotify del usuario.

## Ejecutar el proyecto

Ejecutar:

```bash
streamlit run dashboard.py
```

Streamlit abrirá la aplicación en el navegador. Normalmente estará disponible en:

```text
http://localhost:8501
```

## Sistema de recomendaciones

El dashboard analiza los artistas presentes en la playlist seleccionada y utiliza Last.fm para obtener artistas similares.

Las recomendaciones reciben un nivel de afinidad basado en la presencia de los artistas originales dentro de la playlist.

Luego Spotify se utiliza para obtener información de los artistas recomendados y crear automáticamente una playlist de descubrimientos.

Las canciones agregadas son validadas para comprobar que realmente pertenezcan al artista recomendado.

## Estado del proyecto

El dashboard funciona actualmente en entorno local.

La adaptación para autenticación multiusuario y despliegue público se encuentra en desarrollo.

## Autor

**Alejo-AS**

GitHub: https://github.com/Alejo-AS