import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from collections import Counter
import pandas as pd
#import matplotlib.pyplot as plt
import plotly.express as px
import requests
import os
from dotenv import load_dotenv
from spotipy.exceptions import SpotifyException


load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")


sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri="http://127.0.0.1:8888/callback",
        scope="""
        user-top-read
        playlist-read-private
        playlist-modify-private
        playlist-modify-public
        """,
        cache_path=".spotify_cache_nuevo",
        show_dialog=False
    ),
    status_forcelist=(500, 502, 503, 504)
)


# Usuario
try:
    usuario = sp.current_user()

except SpotifyException as e:

    if e.http_status == 429:

        retry_after = e.headers.get("Retry-After")

        if retry_after:
            minutos_espera = round(int(retry_after) / 60)

            st.error(
                f"Spotify alcanzó temporalmente el límite de solicitudes. "
                f"Intentá nuevamente en aproximadamente {minutos_espera} minutos."
            )
        else:
            st.error(
                "Spotify alcanzó temporalmente el límite de solicitudes. "
                "Intentá nuevamente más tarde."
            )

        st.stop()

    else:
        raise


st.title("🎧 Spotify Dashboard")

st.write(
    f"Usuario: **{usuario['display_name']}**"
)


# Selector de período
opciones = {
    "Últimas semanas": "short_term",
    "Últimos meses": "medium_term",
    "Histórico": "long_term"
}


seleccion = st.selectbox(
    "Periodo de análisis",
    opciones.keys()
)


periodo = opciones[seleccion]


# ======================
# SELECCIÓN DE PLAYLIST
# ======================

@st.cache_data(ttl=3600, show_spinner=False)
def obtener_playlists(usuario_id):

    resultado = sp.current_user_playlists()

    return resultado["items"]


playlists = obtener_playlists(
    usuario["id"]
)


playlist_dict = {
    playlist["name"]: playlist["id"]
    for playlist in playlists
    if playlist["owner"]["id"] == usuario["id"]
}


seleccion_playlist = st.selectbox(
    "Seleccionar playlist",
    playlist_dict.keys()
)

playlist_id = playlist_dict[seleccion_playlist]

st.write("Playlist seleccionada:")
st.write(seleccion_playlist)

# ======================
# CANCIONES SEGÚN PLAYLIST
# ======================

@st.cache_data(ttl=3600, show_spinner="Cargando canciones de Spotify...")
def obtener_canciones_playlist(playlist_id):

    canciones = []

    resultado = sp.playlist_items(
        playlist_id,
        limit=100
    )

    while resultado:

        for elemento in resultado["items"]:

            cancion = elemento.get("item")

            if cancion is not None:
                canciones.append(cancion)

        if resultado["next"]:
            resultado = sp.next(resultado)
        else:
            break

    return canciones


try:
    canciones = obtener_canciones_playlist(playlist_id)

except SpotifyException as e:

    if e.http_status == 429:

        retry_after = e.headers.get("Retry-After") if e.headers else None

        if retry_after:
            minutos_espera = round(int(retry_after) / 60)

            st.error(
                f"Spotify alcanzó temporalmente el límite de solicitudes. "
                f"Intentá nuevamente en aproximadamente {minutos_espera} minutos."
            )
        else:
            st.error(
                "Spotify alcanzó temporalmente el límite de solicitudes. "
                "Intentá nuevamente más tarde."
            )

        st.stop()

    else:
        raise


st.write(
    "Canciones cargadas:",
    len(canciones)
)

# ======================
# DURACIÓN TOTAL
# ======================

duracion_total = sum(
    cancion["duration_ms"]
    for cancion in canciones
)


horas = duracion_total // 3600000

minutos = (duracion_total % 3600000) // 60000

# ======================
# ARTISTAS
# ======================

artistas = []

for cancion in canciones:
    artistas.append(
        cancion["artists"][0]["name"]
    )

ranking = Counter(artistas)

# ======================
# RECOMENDACIONES
# ======================

artistas_existentes = set(artistas)


top_artistas = [
    artista[0]
    for artista in ranking.most_common(10)
]


recomendaciones = []


@st.cache_data(ttl=86400, show_spinner=False)
def obtener_similares_lastfm(artista):

    parametros = {
        "method": "artist.getsimilar",
        "artist": artista,
        "api_key": LASTFM_API_KEY,
        "format": "json"
    }

    respuesta = requests.get(
        "https://ws.audioscrobbler.com/2.0/",
        params=parametros,
        timeout=10
    )

    respuesta.raise_for_status()

    datos = respuesta.json()

    if "similarartists" in datos:
        return datos["similarartists"]["artist"][:10]

    return []


for artista in top_artistas:

    bandas_similares = obtener_similares_lastfm(artista)

    for banda in bandas_similares:

        nombre = banda["name"]

        # Evitar recomendar bandas que ya escuchás
        if nombre not in artistas_existentes:

            recomendaciones.append(
                {
                    "banda": nombre,
                    "origen": artista,
                    "peso": ranking[artista]
                }
            )


afinidad = Counter()

for recomendacion in recomendaciones:

    afinidad[
        recomendacion["banda"]
    ] += recomendacion["peso"]

# ======================
# PORCENTAJE DE AFINIDAD
# ======================

max_afinidad = max(afinidad.values())


afinidad_porcentaje = {}


for banda, puntos in afinidad.items():

    afinidad_porcentaje[banda] = round(
        (puntos / max_afinidad) * 100,
        1
    )

# Guardar motivos de recomendación

motivos = {}


for recomendacion in recomendaciones:

    banda = recomendacion["banda"]

    if banda not in motivos:
        motivos[banda] = []


    motivos[banda].append(
        (
            recomendacion["origen"],
            recomendacion["peso"]
        )
    )


# ======================
# FUNCIONES PLAYLIST
# ======================

def crear_playlist_recomendaciones():

    playlist = sp._post(
        "me/playlists",
        payload={
            "name": "🎸 Descubrimientos recomendados",
            "public": True,
            "description": "Playlist generada desde Spotify Dashboard"
        }
    )

    return playlist["id"]


def obtener_canciones_bandas(bandas):

    canciones_playlist = []

    for banda in bandas:

        try:
            resultado = sp.search(
                q=f"artist:{banda}",
                type="track",
                limit=3
            )

        except SpotifyException as e:

            if e.http_status == 429:

                retry_after = e.headers.get("Retry-After") if e.headers else None

                if retry_after:
                    minutos_espera = round(int(retry_after) / 60)

                    st.error(
                        f"Spotify alcanzó temporalmente el límite de solicitudes. "
                        f"Intentá nuevamente en aproximadamente {minutos_espera} minutos."
                    )
                else:
                    st.error(
                        "Spotify alcanzó temporalmente el límite de solicitudes. "
                        "Intentá nuevamente más tarde."
                    )

                st.stop()

            else:
                raise

        for track in resultado["tracks"]["items"]:

            coincide_artista = any(
                artista["name"].strip().casefold() == banda.strip().casefold()
                for artista in track["artists"]
            )

            if coincide_artista:
                canciones_playlist.append(
                    track["uri"]
                )

    return canciones_playlist


# ======================
# GÉNEROS MUSICALES
# ======================

ids_artistas = []

for cancion in canciones:

    ids_artistas.append(
        cancion["artists"][0]["id"]
    )


ids_artistas = list(set(ids_artistas))

#Para el gráfico de distribución de artistas de toda la playlist

df_todos_artistas = pd.DataFrame(
    ranking.items(),
    columns=["Artista", "Cantidad"]
)

cantidad_artistas = len(ranking)
promedio_artista = len(canciones) / len(ranking)

# ======================
# ÁLBUMES
# ======================

albumes = []

for cancion in canciones:
    albumes.append(
        cancion["album"]["name"]
    )


ranking_albumes = Counter(albumes)
cantidad_albumes = len(ranking_albumes)

album_top = ranking_albumes.most_common(1)[0]

# ======================
# AÑOS DE LANZAMIENTO
# ======================

años = []

for cancion in canciones:

    fecha = cancion["album"].get("release_date")

    if fecha:
        año = int(fecha[:4])
        años.append(año)


decadas = []

for año in años:

    decada = (año // 10) * 10

    decadas.append(
        f"{decada}s"
    )


df_decadas = pd.DataFrame(
    Counter(decadas).items(),
    columns=["Década", "Cantidad"]
)

# ======================
# MÉTRICAS PRINCIPALES
# ======================

artista_top = ranking.most_common(1)[0]


col1, col2, col3, col4 = st.columns(4)


with col1:
    st.metric(
        "🎧 Canciones analizadas",
        len(canciones)
    )


with col2:
    st.metric(
        "🎤 Artista principal",
        artista_top[0]
    )


with col3:
    st.metric(
        "🔁 Repeticiones",
        artista_top[1]
    )

with col4:
    st.metric(
        "💿 Álbum principal",
        album_top[0],
        f"{album_top[1]} canciones"
    )

col5, col6, col7, col8 = st.columns(4)

with col5:
    st.metric(
        "🎸 Artistas diferentes",
        cantidad_artistas
    )


with col6:
    st.metric(
        "💿 Álbumes diferentes",
        cantidad_albumes
    )

with col7:
    st.metric(
        "⏱️ Duración total",
        f"{horas}h {minutos}m"
    )

with col8:
    st.metric(
        "📊 Promedio por artista",
        f"{promedio_artista:.1f}"
    )

df_artistas = pd.DataFrame(
    ranking.most_common(10),
    columns=["Artista", "Cantidad"]
)


st.subheader("🎤 Artistas más escuchados")


fig = px.bar(
    df_artistas.sort_values("Cantidad"),
    x="Cantidad",
    y="Artista",
    orientation="h",
    title="Artistas más escuchados",
    text="Cantidad"
)


st.plotly_chart(fig)

# ======================
# DISTRIBUCIÓN DE ARTISTAS
# ======================

st.subheader("📊 Distribución de artistas")

# ======================
# DISTRIBUCIÓN DE ARTISTAS
# ======================

df_pie = df_todos_artistas.copy()


top = df_pie.sort_values(
    "Cantidad",
    ascending=False
).head(5)


otros = pd.DataFrame({
    "Artista": ["Otros"],
    "Cantidad": [
        df_pie["Cantidad"].sum() - top["Cantidad"].sum()
    ]
})


df_pie_final = pd.concat(
    [top, otros]
)


fig_pie = px.pie(
    df_todos_artistas,
    names="Artista",
    values="Cantidad",
    title="Distribución total de artistas",
    #hole=0.35
)


fig_pie.update_traces(
    textposition="inside",
    textinfo="percent"
)


st.plotly_chart(fig_pie)

# ======================
# DISTRIBUCIÓN POR DÉCADA
# ======================

st.subheader("📅 Distribución por década")


fig_decadas = px.bar(
    df_decadas,
    x="Década",
    y="Cantidad",
    text="Cantidad",
    title="Canciones por década"
)


st.plotly_chart(fig_decadas)

# ======================
# ÁLBUMES CON PORTADAS
# ======================

st.subheader("💿 Álbumes más escuchados")


albumes_mostrados = {}


for cancion in canciones:

    album = cancion["album"]["name"]

    if album not in albumes_mostrados:
        albumes_mostrados[album] = {
            "imagen": cancion["album"]["images"][0]["url"],
            "artista": cancion["artists"][0]["name"]
        }


top_albumes = ranking_albumes.most_common(5)


columnas = st.columns(5)


for columna, (album, cantidad) in zip(columnas, top_albumes):

    with columna:

        st.image(
            albumes_mostrados[album]["imagen"],
            width=130
        )

        st.write(
            f"**{album}**"
        )

        st.write(
            albumes_mostrados[album]["artista"]
        )

        st.write(
            f"🎵 {cantidad} canciones"
        )


# ======================
# OBTENER IMÁGENES DE BANDAS RECOMENDADAS
# ======================

@st.cache_data(ttl=86400, show_spinner=False)
def buscar_artista_spotify(banda):

    resultado = sp.search(
        q=f"artist:{banda}",
        type="artist",
        limit=10
    )

    artistas_encontrados = resultado["artists"]["items"]

    for artista in artistas_encontrados:

        # Verificación exacta para evitar confundir artistas
        if artista["name"].lower() == banda.lower():

            imagen = None

            if artista["images"]:
                imagen = artista["images"][0]["url"]

            link = artista["external_urls"]["spotify"]

            return {
                "imagen": imagen,
                "link": link
            }

    return None


imagenes_recomendaciones = {}
links_recomendaciones = {}


for banda, puntos in afinidad.most_common(10):

    try:
        artista_spotify = buscar_artista_spotify(banda)

    except SpotifyException as e:

        if e.http_status == 429:

            retry_after = e.headers.get("Retry-After") if e.headers else None

            if retry_after:
                minutos_espera = round(int(retry_after) / 60)

                st.error(
                    f"Spotify alcanzó temporalmente el límite de solicitudes. "
                    f"Intentá nuevamente en aproximadamente {minutos_espera} minutos."
                )
            else:
                st.error(
                    "Spotify alcanzó temporalmente el límite de solicitudes. "
                    "Intentá nuevamente más tarde."
                )

            st.stop()

        else:
            raise

    if artista_spotify is not None:

        if artista_spotify["imagen"] is not None:
            imagenes_recomendaciones[banda] = artista_spotify["imagen"]

        links_recomendaciones[banda] = artista_spotify["link"]


# ======================
# BANDAS RECOMENDADAS
# ======================

st.subheader("🎸 Bandas recomendadas para vos")


columnas = st.columns(5)


for columna, (banda, puntos) in zip(
    columnas,
    afinidad.most_common(10)
):

    with columna:

        if banda in imagenes_recomendaciones:

            st.image(
                imagenes_recomendaciones[banda],
                width=130
            )


        st.write(
            f"**{banda}**"
        )


        st.write(
            f"⭐ Afinidad: {afinidad_porcentaje[banda]}%"
        )
        
        st.progress(
            afinidad_porcentaje[banda] / 100
        )

        if banda in links_recomendaciones:

            st.link_button(
                "▶ Abrir en Spotify",
                links_recomendaciones[banda]
            )    

        st.write(
            "Recomendado por:"
        )


        for origen, peso in sorted(
            motivos[banda],
            key=lambda x: x[1],
            reverse=True
        )[:3]:

            st.write(
                f"• {origen} ({peso} canciones)"
            )

# ======================
# CREAR PLAYLIST AUTOMÁTICA
# ======================

st.divider()


if st.button(
    "🎧 Crear playlist de descubrimientos",
    key="crear_playlist"
):

    bandas = [
        banda
        for banda, puntos in afinidad.most_common(10)
    ]


    playlist_id = crear_playlist_recomendaciones()


    tracks = obtener_canciones_bandas(
        bandas
    )


    sp.playlist_add_items(
        playlist_id,
        tracks
    )


    st.success(
        "Playlist creada correctamente en Spotify 🎸"
    )



# ======================
# TABLA DE CANCIONES
# ======================

st.subheader("🎵 Listado de canciones de la playlist")


tabla = []


for cancion in canciones:

    tabla.append(
        {
            "Canción": cancion["name"],
            "Artista": cancion["artists"][0]["name"],
            "Álbum": cancion["album"]["name"]
        }
    )


df = pd.DataFrame(tabla)


st.dataframe(df)