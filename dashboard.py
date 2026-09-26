import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from collections import Counter
import pandas as pd
import plotly.express as px
import requests
import os
from dotenv import load_dotenv
from spotipy.exceptions import SpotifyException
from spotipy.cache_handler import CacheHandler
import hashlib
import hmac
import secrets
import json
from streamlit_cookies_manager import EncryptedCookieManager
import time
import unicodedata

st.set_page_config(
    page_title="Spotify Dashboard",
    page_icon="🎧",
    layout="centered",
    initial_sidebar_state="collapsed"
)

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

COOKIES_PASSWORD = os.getenv("COOKIES_PASSWORD")


cookies = EncryptedCookieManager(
    prefix="spotify-dashboard/",
    password=COOKIES_PASSWORD
)

if not cookies.ready():
    st.stop()

class StreamlitCacheHandler(CacheHandler):

    def __init__(self, cookies):
        self.cookies = cookies

    def get_cached_token(self):

        # Primero buscar en la sesión actual
        token_info = st.session_state.get("spotify_token")

        if token_info:
            return token_info

        # Si hubo F5, recuperar el token desde la cookie cifrada
        token_cookie = self.cookies.get("spotify_token")

        if token_cookie:

            try:
                token_info = json.loads(token_cookie)

                st.session_state["spotify_token"] = token_info

                return token_info

            except (json.JSONDecodeError, TypeError):
                return None

        return None


    def save_token_to_cache(self, token_info):

        # Guardar en la sesión actual
        st.session_state["spotify_token"] = token_info

        # Guardar también cifrado en el navegador
        self.cookies["spotify_token"] = json.dumps(token_info)

        self.cookies.save()


REDIRECT_URI = os.getenv(
    "REDIRECT_URI",
    "http://127.0.0.1:8501/"
)

SCOPE = [
    "user-top-read",
    "playlist-read-private",
    "playlist-modify-private",
    "playlist-modify-public"
]

def generar_estado_oauth():
    nonce = secrets.token_urlsafe(24)

    firma = hmac.new(
        CLIENT_SECRET.encode(),
        nonce.encode(),
        hashlib.sha256
    ).hexdigest()

    return f"{nonce}.{firma}"


def estado_oauth_valido(estado):

    if not estado or "." not in estado:
        return False

    nonce, firma_recibida = estado.rsplit(".", 1)

    firma_correcta = hmac.new(
        CLIENT_SECRET.encode(),
        nonce.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(
        firma_recibida,
        firma_correcta
    )


cache_handler = StreamlitCacheHandler(cookies)


auth_manager = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE,
    cache_handler=cache_handler,
    show_dialog=False,
    open_browser=False
)


# ======================
# CALLBACK DE SPOTIFY
# ======================

if "error" in st.query_params:

    st.error(
        f"Spotify rechazó la autorización: "
        f"{st.query_params['error']}"
    )

    st.stop()


if "code" in st.query_params:

    codigo = st.query_params["code"]
    estado = st.query_params.get("state")

    if not estado_oauth_valido(estado):

        st.error(
            "No se pudo validar el inicio de sesión de Spotify."
        )

        st.stop()

    auth_manager.get_access_token(
        code=codigo,
        check_cache=False
    )

    st.query_params.clear()

    st.rerun()


# ======================
# COMPROBAR AUTENTICACIÓN
# ======================

token_info = auth_manager.validate_token(
    cache_handler.get_cached_token()
)


if token_info is None:

    estado = generar_estado_oauth()

    url_autorizacion = auth_manager.get_authorize_url(
        state=estado
    )

    st.title("🎧 Spotify Dashboard")

    st.write(
        "Conectá tu cuenta de Spotify para utilizar el dashboard."
    )

    st.link_button(
        "Conectar con Spotify",
        url_autorizacion
    )

    st.stop()


sp = spotipy.Spotify(
    auth_manager=auth_manager,
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


# ======================
# CERRAR SESIÓN
# ======================

# ======================
# MENÚ DE CUENTA
# ======================

with st.popover("⚙️ Cuenta"):

    st.write(f"Conectado como **{usuario['display_name']}**")

    if st.button(
        "🚪 Desconectar Spotify",
        key="desconectar_spotify"
    ):

        st.session_state.pop("spotify_token", None)

        cookies["spotify_token"] = ""
        cookies.save()

        time.sleep(1)

        st.query_params.clear()

        st.rerun()

st.title("🎧 Spotify Dashboard")

st.write(
    f"Usuario: **{usuario['display_name']}**"
)


# ======================
# MODO DE ANÁLISIS
# ======================

modo = st.radio(
    "Modo de análisis",
    [
        "👤 Mi perfil musical",
        "📊 Analizar playlist"
    ],
    horizontal=True
)


# ======================
# SELECTOR DE PERÍODO
# ======================

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
# PERFIL MUSICAL
# ======================

def normalizar_nombre(nombre):
    nombre = unicodedata.normalize(
        "NFKD",
        nombre
    )

    nombre = "".join(
        caracter
        for caracter in nombre
        if not unicodedata.combining(caracter)
    )

    return " ".join(
        nombre.casefold().split()
    )

@st.cache_data(ttl=3600, show_spinner=False)
def obtener_top_artistas(usuario_id, periodo):

    resultado = sp.current_user_top_artists(
        limit=20,
        time_range=periodo
    )

    return resultado["items"]


@st.cache_data(ttl=3600, show_spinner=False)
def obtener_top_canciones(usuario_id, periodo):

    resultado = sp.current_user_top_tracks(
        limit=20,
        time_range=periodo
    )

    return resultado["items"]

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

@st.cache_data(ttl=604800, show_spinner=False)
def buscar_spotify_por_mbid(mbid):

    if not mbid:
        return None

    respuesta = requests.get(
        f"https://musicbrainz.org/ws/2/artist/{mbid}",
        params={
            "inc": "url-rels",
            "fmt": "json"
        },
        headers={
            "User-Agent": (
                "spotify-dashboard/1.0 "
                "(https://github.com/Alejo-AS/spotify-dashboard)"
            )
        },
        timeout=10
    )

    if respuesta.status_code != 200:
        return None

    datos = respuesta.json()

    for relacion in datos.get("relations", []):

        recurso = (
            relacion
            .get("url", {})
            .get("resource", "")
        )

        if "open.spotify.com/artist/" in recurso:

            spotify_id = (
                recurso
                .split("open.spotify.com/artist/", 1)[1]
                .split("?", 1)[0]
                .split("/", 1)[0]
            )

            artista = sp.artist(
                spotify_id
            )

            imagen = None

            if artista.get("images"):
                imagen = artista["images"][0]["url"]

            return {
                "imagen": imagen,
                "link": artista["external_urls"]["spotify"],
                "id": artista["id"]
            }

    return None

# ======================
# OBTENER IMÁGENES DE BANDAS RECOMENDADAS
# ======================

@st.cache_data(ttl=86400, show_spinner=False)
def buscar_artista_spotify(banda, mbid=""):

    # ======================
    # 1. INTENTAR POR MBID
    # ======================

    if mbid:

        artista_mbid = buscar_spotify_por_mbid(
            mbid
        )

        if artista_mbid is not None:
            return artista_mbid


    # ======================
    # 2. FALLBACK POR NOMBRE
    # ======================

    nombre_objetivo = normalizar_nombre(
        banda
    )

    # Primera búsqueda: filtro específico por artista
    resultado = sp.search(
        q=f'artist:"{banda}"',
        type="artist",
        limit=10
    )

    candidatos = []
    ids_encontrados = set()

    for artista in resultado["artists"]["items"]:

        if (
            normalizar_nombre(artista["name"])
            == nombre_objetivo
            and artista["id"] not in ids_encontrados
        ):

            candidatos.append(artista)
            ids_encontrados.add(artista["id"])


    # Segunda búsqueda: nombre general
    # Sirve para casos donde el filtro artist:
    # no devuelve correctamente el perfil esperado.
    resultado_general = sp.search(
        q=banda,
        type="artist",
        limit=10
    )

    for artista in resultado_general["artists"]["items"]:

        if (
            normalizar_nombre(artista["name"])
            == nombre_objetivo
            and artista["id"] not in ids_encontrados
        ):

            candidatos.append(artista)
            ids_encontrados.add(artista["id"])


    if not candidatos:
        return None


    # Si hay una sola coincidencia exacta,
    # usamos ese perfil.
    if len(candidatos) == 1:

        artista = candidatos[0]

        imagen = None

        if artista.get("images"):
            imagen = artista["images"][0]["url"]

        return {
            "imagen": imagen,
            "link": artista["external_urls"]["spotify"],
            "id": artista["id"]
        }


    # Si hay varios artistas con exactamente
    # el mismo nombre y el MBID no permitió
    # resolverlo, preferimos no adivinar.
    return None


if modo == "👤 Mi perfil musical":

    st.header("👤 Mi perfil musical")

    try:

        top_artistas_perfil = obtener_top_artistas(
            usuario["id"],
            periodo
        )

        top_canciones_perfil = obtener_top_canciones(
            usuario["id"],
            periodo
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
                    "Spotify alcanzó temporalmente el límite de solicitudes."
                )

            st.stop()

        else:
            raise


    if not top_artistas_perfil or not top_canciones_perfil:

        st.info(
            "Spotify todavía no dispone de suficientes datos "
            "para generar este análisis."
        )

        st.stop()


    # ======================
    # COMPARACIÓN TEMPORAL
    # ======================

    try:

        artistas_short = obtener_top_artistas(
            usuario["id"],
            "short_term"
        )

        artistas_medium = obtener_top_artistas(
            usuario["id"],
            "medium_term"
        )

        artistas_long = obtener_top_artistas(
            usuario["id"],
            "long_term"
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
                    "Spotify alcanzó temporalmente el límite de solicitudes."
                )

            st.stop()

        else:
            raise


    nombres_short = {
        artista["name"]
        for artista in artistas_short
    }

    nombres_medium = {
        artista["name"]
        for artista in artistas_medium
    }

    nombres_long = {
        artista["name"]
        for artista in artistas_long
    }


    artistas_recientes = [
        artista["name"]
        for artista in artistas_short
        if artista["name"] not in nombres_long
    ]


    artistas_constantes = [
        artista["name"]
        for artista in artistas_long
        if (
            artista["name"] in nombres_short
            and artista["name"] in nombres_medium
        )
    ]


    artistas_anteriores = [
        artista["name"]
        for artista in artistas_long
        if artista["name"] not in nombres_short
    ]


    # ======================
    # DÉCADAS
    # ======================

    decadas_perfil = []

    for cancion in top_canciones_perfil:

        fecha = cancion["album"].get("release_date")

        if fecha:
            año = int(fecha[:4])
            decada = (año // 10) * 10

            decadas_perfil.append(
                f"{decada}s"
            )


    if decadas_perfil:

        decada_principal = Counter(
            decadas_perfil
        ).most_common(1)[0][0]

    else:

        decada_principal = "Sin datos"


    # ======================
    # MÉTRICAS
    # ======================

    # Primera fila
    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "🎤 Artista principal",
            top_artistas_perfil[0]["name"]
        )

    with col2:
        st.metric(
            "🎵 Canción principal",
            top_canciones_perfil[0]["name"]
        )


    # Segunda fila
    col3, col4 = st.columns(2)

    with col3:
        st.metric(
            "🎸 Artistas analizados",
            len(top_artistas_perfil)
        )

    with col4:
        st.metric(
            "📅 Década predominante",
            decada_principal
        )

    # ======================
    # EVOLUCIÓN DE GUSTOS
    # ======================

    st.subheader("📈 Evolución de tus gustos")

    col_recientes, col_constantes, col_anteriores = st.columns(3)


    with col_recientes:

        st.write("### 🆕 Artistas recientes")

        if artistas_recientes:

            for artista in artistas_recientes[:8]:
                st.write(f"• {artista}")

        else:
            st.write("No aparecen cambios destacados.")


    with col_constantes:

        st.write("### ❤️ Artistas constantes")

        if artistas_constantes:

            for artista in artistas_constantes[:8]:
                st.write(f"• {artista}")

        else:
            st.write("No hay artistas presentes en los tres períodos.")


    with col_anteriores:

        st.write("### 🕰️ Etapa anterior")

        if artistas_anteriores:

            for artista in artistas_anteriores[:8]:
                st.write(f"• {artista}")

        else:
            st.write("No aparecen cambios destacados.")


    # ======================
    # RECOMENDACIONES SEGÚN EL PERFIL
    # ======================

    st.subheader("🎸 Recomendaciones según tu perfil")

    recomendaciones_perfil = []

    # Artistas que ya forman parte del Top del usuario
    artistas_top_perfil = {
        artista["name"].strip().casefold()
        for artista in top_artistas_perfil
    }


    # Usamos los 10 artistas principales como origen
    for posicion, artista in enumerate(
        top_artistas_perfil[:10],
        start=1
    ):

        nombre_artista = artista["name"]

        # Cuanto más arriba está en el ranking,
        # mayor peso tiene para las recomendaciones.
        peso = 11 - posicion

        bandas_similares = obtener_similares_lastfm(
            nombre_artista
        )

        for banda in bandas_similares:

            nombre_banda = banda["name"]

            # Evitar recomendar artistas que ya están
            # entre los principales del usuario
            if nombre_banda.strip().casefold() not in artistas_top_perfil:

                recomendaciones_perfil.append(
                    {
                        "banda": nombre_banda,
                        "mbid": banda.get("mbid", ""),
                        "origen": nombre_artista,
                        "peso": peso
                    }
                )


    # ======================
    # CALCULAR AFINIDAD
    # ======================

    afinidad_perfil = Counter()

    for recomendacion in recomendaciones_perfil:

        afinidad_perfil[
            recomendacion["banda"]
        ] += recomendacion["peso"]


    # ======================
    # GUARDAR MBID DE CADA BANDA
    # ======================

    mbid_por_banda = {}

    for recomendacion in recomendaciones_perfil:

        if recomendacion.get("mbid"):

            mbid_por_banda.setdefault(
                recomendacion["banda"],
                recomendacion["mbid"]
            )

    # ======================
    # MOTIVOS
    # ======================

    motivos_perfil = {}

    for recomendacion in recomendaciones_perfil:

        banda = recomendacion["banda"]

        if banda not in motivos_perfil:
            motivos_perfil[banda] = []

        motivos_perfil[banda].append(
            (
                recomendacion["origen"],
                recomendacion["peso"]
            )
        )


    # ======================
    # MOSTRAR RECOMENDACIONES
    # ======================

    if afinidad_perfil:

        max_afinidad_perfil = max(
            afinidad_perfil.values()
        )

        top_recomendaciones_perfil = afinidad_perfil.most_common(10)

        recomendaciones_visual = []

        for banda, puntos in top_recomendaciones_perfil:

            porcentaje = round(
                (puntos / max_afinidad_perfil) * 100,
                1
            )

            try:
                artista_spotify = buscar_artista_spotify(
                banda,
                mbid_por_banda.get(banda, "")
            )

            except SpotifyException as e:

                if e.http_status == 429:

                    retry_after = e.headers.get("Retry-After") if e.headers else None

                    if retry_after:
                        minutos_espera = round(
                            int(retry_after) / 60
                        )

                        st.error(
                            f"Spotify alcanzó temporalmente el límite de solicitudes. "
                            f"Intentá nuevamente en aproximadamente "
                            f"{minutos_espera} minutos."
                        )
                    else:
                        st.error(
                            "Spotify alcanzó temporalmente el límite de solicitudes."
                        )

                    st.stop()

                else:
                    raise

            recomendaciones_visual.append(
                {
                    "banda": banda,
                    "porcentaje": porcentaje,
                    "spotify": artista_spotify
                }
            )


        for inicio in range(
            0,
            len(recomendaciones_visual),
            5
        ):

            grupo = recomendaciones_visual[
                inicio:inicio + 5
            ]

            columnas = st.columns(5)

            for columna, recomendacion in zip(
                columnas,
                grupo
            ):

                banda = recomendacion["banda"]
                porcentaje = recomendacion["porcentaje"]
                artista_spotify = recomendacion["spotify"]

                with columna:

                    if (
                        artista_spotify is not None
                        and artista_spotify["imagen"] is not None
                    ):

                        st.image(
                            artista_spotify["imagen"],
                            width=130
                        )

                    st.write(
                        f"**{banda}**"
                    )

                    st.write(
                        f"⭐ Afinidad: {porcentaje}%"
                    )

                    st.progress(
                        porcentaje / 100
                    )

                    if artista_spotify is not None:

                        st.link_button(
                            "▶ Abrir en Spotify",
                            artista_spotify["link"]
                        )

                    st.write(
                        "Recomendado por:"
                    )

                    for origen, peso in sorted(
                        motivos_perfil[banda],
                        key=lambda x: x[1],
                        reverse=True
                    )[:3]:

                        st.write(
                            f"• {origen}"
                        )

    else:

        st.info(
            "No se encontraron recomendaciones suficientes "
            "para este período."
        )

    # ======================
    # TOP ARTISTAS
    # ======================

    st.subheader("🎤 Tus artistas principales")

    columnas = st.columns(5)

    for columna, artista in zip(
        columnas,
        top_artistas_perfil[:5]
    ):

        with columna:

            if artista["images"]:
                st.image(
                    artista["images"][0]["url"],
                    width=130
                )

            st.write(
                f"**{artista['name']}**"
            )


    tabla_artistas = []

    for posicion, artista in enumerate(
        top_artistas_perfil,
        start=1
    ):

        tabla_artistas.append({
            "Posición": posicion,
            "Artista": artista["name"]
        })


    st.dataframe(
        pd.DataFrame(tabla_artistas),
        hide_index=True
    )


    # ======================
    # TOP CANCIONES
    # ======================

    st.subheader("🎵 Tus canciones principales")

    tabla_canciones = []

    for posicion, cancion in enumerate(
        top_canciones_perfil,
        start=1
    ):

        tabla_canciones.append({
            "Posición": posicion,
            "Canción": cancion["name"],
            "Artista": cancion["artists"][0]["name"],
            "Álbum": cancion["album"]["name"]
        })


    st.dataframe(
        pd.DataFrame(tabla_canciones),
        hide_index=True
    )


    # ======================
    # DISTRIBUCIÓN POR DÉCADA
    # ======================

    st.subheader("📅 Décadas de tus canciones principales")

    df_decadas_perfil = pd.DataFrame(
        Counter(decadas_perfil).items(),
        columns=["Década", "Cantidad"]
    )

    if not df_decadas_perfil.empty:

        df_decadas_perfil = df_decadas_perfil.sort_values(
            "Década"
        )

        fig_decadas_perfil = px.bar(
            df_decadas_perfil,
            x="Década",
            y="Cantidad",
            text="Cantidad",
            title="Distribución por década"
        )

        st.plotly_chart(
            fig_decadas_perfil,
            use_container_width=True
        )


    # Evita ejecutar abajo el análisis de playlists
    st.stop()


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

#st.write("Playlist seleccionada:")
#st.write(seleccion_playlist)

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


#st.write(
   # "Canciones cargadas:",
    #len(canciones)
#)

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
                    "mbid": banda.get("mbid", ""),
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
# GUARDAR MBID DE CADA BANDA
# ======================

mbid_por_banda_playlist = {}

for recomendacion in recomendaciones:

    if recomendacion.get("mbid"):

        mbid_por_banda_playlist.setdefault(
            recomendacion["banda"],
            recomendacion["mbid"]
        )


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


def calcular_cupos_bandas(bandas_con_afinidad, total_objetivo=50):

    # Mínimo de 3 canciones por banda
    cupos = {
        banda: 3
        for banda, puntos in bandas_con_afinidad
    }

    canciones_asignadas = sum(cupos.values())
    restantes = total_objetivo - canciones_asignadas

    # Repartir los lugares restantes según afinidad
    while restantes > 0:

        candidatos = [
            (banda, puntos)
            for banda, puntos in bandas_con_afinidad
            if cupos[banda] < 10
        ]

        if not candidatos:
            break

        banda_elegida = max(
            candidatos,
            key=lambda x: x[1] / cupos[x[0]]
        )[0]

        cupos[banda_elegida] += 1
        restantes -= 1

    return cupos


def obtener_canciones_bandas(bandas_con_afinidad):

    canciones_playlist = []
    canciones_agregadas = set()

    cupos = calcular_cupos_bandas(
        bandas_con_afinidad,
        total_objetivo=50
    )

    for banda, puntos in bandas_con_afinidad:

        try:
            resultado = sp.search(
                q=f"artist:{banda}",
                type="track",
                limit=10
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

        cantidad_banda = 0

        for track in resultado["tracks"]["items"]:

            coincide_artista = any(
                artista["name"].strip().casefold() == banda.strip().casefold()
                for artista in track["artists"]
            )

            if not coincide_artista:
                continue

            if track["uri"] in canciones_agregadas:
                continue

            canciones_playlist.append(
                track["uri"]
            )

            canciones_agregadas.add(
                track["uri"]
            )

            cantidad_banda += 1

            if cantidad_banda >= cupos[banda]:
                break

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

df_decadas = df_decadas.sort_values(
    "Década"
)

# ======================
# MÉTRICAS PRINCIPALES
# ======================

artista_top = ranking.most_common(1)[0]


# Primera fila
col1, col2 = st.columns(2)

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


# Segunda fila
col3, col4 = st.columns(2)

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


# Tercera fila
col5, col6 = st.columns(2)

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


# Cuarta fila
col7, col8 = st.columns(2)

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


imagenes_recomendaciones = {}
links_recomendaciones = {}


for banda, puntos in afinidad.most_common(10):

    try:
        artista_spotify = buscar_artista_spotify(
        banda,
        mbid_por_banda_playlist.get(banda, "")
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

    bandas_con_afinidad = afinidad.most_common(10)

    playlist_id = crear_playlist_recomendaciones()

    tracks = obtener_canciones_bandas(
        bandas_con_afinidad
    )

    sp.playlist_add_items(
        playlist_id,
        tracks
    )

    st.success(
        f"Playlist creada correctamente con {len(tracks)} canciones 🎸"
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