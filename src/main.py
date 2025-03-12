import ctypes
import time
import os
import datetime

import win32gui
import win32process
from pypresence import Presence

from const import BASE, class_names, game_state_messages, overlay_files
from data import read_str, read_str_short, read_uint, read_byte_array, read_int, read_float, read_uchar


# Direcciones específicas de misiones de enfrentamiento
PVP_MISSION_ADDRESSES = [
    0x08F33BBC,  # Dirección proporcionada por el usuario
    # Puedes añadir más direcciones específicas de misiones de enfrentamiento aquí
]


def is_pvp_mission(data, multi_pointer):
   # print("HOLAAAAAAAAAAAAAAAAAA")
    """Comprueba si estamos en una misión de enfrentamiento"""
    # Comprobar si estamos en una misión
    overlay_file_addr = 0x08ABB1A0 - BASE
    overlay_file = read_str(data, overlay_file_addr)
    
    if overlay_file != "OL_Azito.bin":
        return False
    
    # Comprobar el valor en la dirección específica
    # try:
    #     pvp_indicator = read_uint(data, 0x08F33BBC - BASE)
    #     if pvp_indicator > 0:  # Ajustar según sea necesario
    #         print(f" - Detectada misión de enfrentamiento (valor en 0x08F33BBC: {pvp_indicator})")
    #         return True
    # except Exception as e:
    #     print(f" - Error al leer indicador de enfrentamiento: {e}")
    
    # Comprobar el nombre de la misión si contiene palabras clave que indican enfrentamiento
    if multi_pointer != 0x0:
        quest_name_addr = multi_pointer - BASE + 0x9FC + 0x100
        try:
            quest_name = read_str_short(data, quest_name_addr)
            pvp_keywords = ["vs", "contra", "enfrentamiento", "duelo", "batalla", "pvp","Enf. múltiple","["]
            
            # Convertir a minúsculas para facilitar la comparación
            lower_quest_name = quest_name.lower()
            
            # Verificar si alguna palabra clave está en el nombre de la misión
            for keyword in pvp_keywords:
                if keyword in lower_quest_name:
                    print(f" - Detectada misión de enfrentamiento por palabra clave: '{keyword}' en '{quest_name}'")
                    return True
        except Exception as e:
            print(f" - Error al leer nombre de misión: {e}")
        
    return False


def find_window(partial_title):
    window_handle = None
    window_titles = []

    def enum_windows_callback(handle, _):
        title = win32gui.GetWindowText(handle)
        if partial_title.lower() in title.lower():
            window_titles.append(title)
            nonlocal window_handle
            window_handle = handle

    win32gui.EnumWindows(enum_windows_callback, None)

    return window_handle, window_titles


def get_process_data():
    window_handle, window_titles = find_window("PPSSPP")

    if window_handle is not None:
        lower = win32gui.SendMessage(window_handle, 0xB118, 0, 2)
        upper = win32gui.SendMessage(window_handle, 0xB118, 0, 3)
        return (upper * 0x100000000) + lower, win32process.GetWindowThreadProcessId(
            window_handle
        )[1]
    return None, None


def print_memory_dump(data, address, size=0x100, row_size=16, title=None):
    """Imprime un dump hexadecimal de memoria para depuración"""
    if title:
        print(f"\n===== {title} =====")
    
    for i in range(0, size, row_size):
        row_data = data[address-BASE+i:address-BASE+i+row_size]
        if not row_data:  # Si no hay datos, saltamos
            continue
            
        # Imprimir dirección y valores hexadecimales
        hex_values = ' '.join([f'{b:02X}' for b in row_data])
        addr_str = f"{address + i:08X}"
        
        # Imprimir caracteres ASCII (si son imprimibles)
        ascii_values = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in row_data])
        
        # Rellenar con espacios si la línea está incompleta
        padding = ' ' * (3 * (row_size - len(row_data)))
        
        print(f"{addr_str}: {hex_values}{padding} | {ascii_values}")


def get_game_data():
    """Obtiene datos del juego y retorna un diccionario con la información"""
   # print("\n" + "="*80)
  #  print(f"# Actualizando datos - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
   # print("="*80)
    
    process_data = get_process_data()
    if not process_data or process_data[0] is None:
        print("No se encontró la ventana de PPSSPP")
        return None
        
    base_address, window_pid = process_data

    if base_address != 0x0:
        OpenProcess = ctypes.windll.kernel32.OpenProcess
        ReadProcessMemory = ctypes.windll.kernel32.ReadProcessMemory
        processHandle = OpenProcess(0x10, False, window_pid)

        # Get base address of the game
        data = ctypes.c_uint32()
        bytes_read = ctypes.c_uint32()
        result = ReadProcessMemory(
            processHandle,
            base_address,
            ctypes.byref(data),
            ctypes.sizeof(data),
            ctypes.byref(bytes_read),
        )

        if result == 0:
            print(f"Error al leer memoria base: {ctypes.GetLastError()}")
            return None

        game_memory_pointer = data.value
       # print(f" - Puntero de memoria del juego: 0x{game_memory_pointer:08X}")

        # Get game memory
        buf_len = 0x1800000  # ~24MB de memoria
        buf = ctypes.create_string_buffer(buf_len)
        read = ctypes.c_size_t()

      #  print(f" - Leyendo {buf_len/1024/1024:.2f}MB de memoria desde 0x{game_memory_pointer + 0x8800000:08X}...")
        
        result = ReadProcessMemory(
            processHandle,
            game_memory_pointer + 0x8800000,
            buf,
            buf_len,
            ctypes.byref(read),
        )

        if result == 0:
            print(f"Error al leer memoria del juego: {ctypes.GetLastError()}")
            return None

        print(f" - Leídos {read.value/1024/1024:.2f}MB de memoria")
        data = bytearray(buf)

        # Crear diccionario para almacenar datos del juego
        game_data = {}

        # Pointer to save pointer location
        base_data_pointer = read_uint(data, 0x2ABD94)
        print(f" - Puntero de datos base: 0x{base_data_pointer:08X}")
        if base_data_pointer == 0x0:
            print(" - El puntero de datos base es nulo, ¿el juego está iniciado?")
            return None

        # Examinar la estructura alrededor del puntero base
        #print_memory_dump(data, base_data_pointer, size=0x200, title=f"Memoria alrededor del puntero base (0x{base_data_pointer:08X})")

        # Pointer to savedata start
        save_pointer = read_uint(data, base_data_pointer - BASE + 0x50)
        print(f" - Puntero de datos de guardado: 0x{save_pointer:08X}")

        # Pointer to multiplayer start
        multi_pointer = read_uint(data, base_data_pointer - BASE + 0x78)
        print(f" - Puntero de datos multijugador: 0x{multi_pointer:08X}")

        # Información sobre el archivo de superposición
        overlay_file_addr = 0x08ABB1A0 - BASE
        overlay_file = read_str(data, overlay_file_addr)
        print(f" - Dirección de archivo de superposición: 0x08ABB1A0")
        print(f" - Archivo de superposición: '{overlay_file}'")
        game_data["overlay_file"] = overlay_file

        # Comprobar si estamos en una misión de enfrentamiento
        is_pvp = is_pvp_mission(data, multi_pointer)
        game_data["is_pvp"] = is_pvp
        
        if is_pvp:
            print(" - ¡MODO DE SIGILO ACTIVADO! Detectada misión de enfrentamiento")
            game_data["stealth_mode"] = True
        else:
            game_data["stealth_mode"] = False

        # Imprimir otros punteros potencialmente útiles
        for offset in range(0, 0x100, 4):
            ptr_value = read_uint(data, base_data_pointer - BASE + offset)
            # if ptr_value != 0:
            #     print(f" - Puntero en offset +0x{offset:02X}: 0x{ptr_value:08X}")

        if save_pointer != 0x00:
            # Información sobre la clase actual
            current_class_addr = save_pointer - BASE + 0x9520
            current_class = read_uint(data, current_class_addr)
            print(f" - Dirección de clase actual: 0x{save_pointer + 0x9520:08X} = {current_class}")
            
            if 0 <= current_class < len(class_names):
                class_name = class_names[current_class]
                print(f" - Clase actual: {class_name} (ID: {current_class})")
                game_data["current_class"] = class_name
                game_data["current_class_id"] = current_class  # Guardar el ID de la clase también
            else:
                print(f" - ¡Clase actual fuera de rango! Valor: {current_class}")
                game_data["current_class"] = f"Unknown({current_class})"
                game_data["current_class_id"] = 0  # ID predeterminado si está fuera de rango
            
            # Buscar más información sobre el personaje del jugador
            player_stats_addr = save_pointer - BASE + 0x9500
            #print_memory_dump(data, save_pointer + 0x9500, size=0x100, title="Estadísticas del jugador")
            
            # Intentar leer nivel del jugador
            try:
                player_level = read_uint(data, save_pointer - BASE + 0x9540)
                print(f" - Nivel del jugador: {player_level}")
                game_data["player_level"] = player_level
            except Exception as e:
                print(f" - Error al leer nivel: {e}")
            
            # Intentar leer HP/experiencia/etc
            try:
                player_exp = read_uint(data, save_pointer - BASE + 0x9544)
                print(f" - Experiencia del jugador: {player_exp}")
                game_data["player_exp"] = player_exp
            except Exception as e:
                print(f" - Error al leer experiencia: {e}")

        if multi_pointer != 0x0:
            # Información sobre la misión actual
            quest_name_addr = multi_pointer - BASE + 0x9FC + 0x100
            quest_name = read_str_short(data, quest_name_addr)
            print(f" - Dirección de nombre de misión: 0x{multi_pointer + 0x9FC + 0x100:08X}")
            print(f" - Nombre de misión actual: '{quest_name}'")
            game_data["current_quest"] = quest_name
            
            # Imprimir bytes alrededor del nombre de la misión para depuración
            #print_memory_dump(data, multi_pointer + 0x9FC, size=0x200, title="Datos de misión")
            
            # Intentar encontrar más información sobre la misión
            try:
                mission_stage = read_uint(data, multi_pointer - BASE + 0xA00)
                print(f" - Etapa de misión: {mission_stage}")
                game_data["mission_stage"] = mission_stage
            except Exception as e:
                print(f" - Error al leer etapa de misión: {e}")
        
        # Imprimir bytes alrededor del nombre del archivo de superposición
       # print_memory_dump(data, 0x08ABB1A0, size=0x100, title="Datos de archivo de superposición")
        
        return game_data
    else:
        print("No se pudo obtener la dirección base del juego")
        return None


def process_game_data(game_data):
    """Procesa los datos del juego para la Rich Presence de Discord"""
    if not game_data:
        return "Esperando juego...", None
    
    # Modo de sigilo para enfrentamientos
    if game_data.get("stealth_mode", False):
        detail = "En enfrentamiento"
        state = "Preparando estrategia"
        return detail, state
        
    overlay = game_data["overlay_file"]

    if overlay == overlay_files["none"] or overlay == overlay_files["title"]:
        detail = "En la pantalla de título"
        state = None
    elif overlay == overlay_files["azito"]:
        detail = f"Clase: {game_data['current_class']}"
        if "player_level" in game_data:
            detail += f" (Nivel {game_data['player_level']})"
        state = f"{game_state_messages[overlay]}"
    elif overlay == overlay_files["mission"]:
        detail = f"Clase: {game_data['current_class']}"
        if "player_level" in game_data:
            detail += f" (Nivel {game_data['player_level']})"
        state = f"{game_state_messages[overlay]}: {game_data['current_quest']}"
    else:
        detail = f"Clase: {game_data.get('current_class', 'Desconocida')}"
        state = f"Estado: {overlay}"

    return detail, state


def get_hero_image(class_id):
    """Retorna la URL de la imagen para cada clase de héroe"""
    # Mapeo de ID de clase a URL de imagen
    hero_images = {
        # Clases principales
        1: "https://ejemplo.com/hatapon.png",      # Hatapon
        2: "https://ejemplo.com/yarida.png",       # Yarida
        3: "https://ejemplo.com/taterazay.png",    # Taterazay
        4: "https://ejemplo.com/yumiyacha.png",    # Yumiyacha
        5: "https://ejemplo.com/kibadda.png",      # Kibadda
        6: "https://ejemplo.com/dekapon.png",      # Dekapon
        7: "https://ejemplo.com/megapon.png",      # Megapon
        8: "https://ejemplo.com/mahopon.png",      # Mahopon
        9: "https://ejemplo.com/destrobo.png",     # Destrobo
        10: "https://ejemplo.com/charipon.png",    # Charipon
        
        # Clases avanzadas
        11: "https://ejemplo.com/chakapon.png",    # Chakapon
        12: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/piek.jpg?v=1741510811191",     # Piekron
        13: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/woo.jpg?v=1741510815788",     # Wooyari
        14: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/pyok.jpg?v=1741510765669",  # Pyokorider
        15: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/cana.jpg?v=1741510792961", # Cannassault
        16: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/char.jpg?v=1741510823818",   # Charibasa
        17: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/guard.jpg?v=1741510782736",    # Guardira
        18: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/tonde.jpg?v=1741509613703",    # Tondenga
        19: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/myam.jpg?v=1741510797904",     # Myamsar
        20: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/bowmun.jpg?v=1741510771534",     # Bowmunk
        
        # Otras clases
        21: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/grenn.jpg?v=1741509959252",    # Grenburr
        22: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/alos.jpg?v=1741510787057",     # Alosson
        23: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/wond.jpg?v=1741510802684", # Wondabarappa
        24: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/jam.jpg?v=1741510779012",      # Jamsch
        25: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/oho.jpg?v=1741510818995",     # Oohoroc
        26: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/kop.jpg?v=1741510806312",     # Pingrek
        27: "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/canno.jpg?v=1741510775617", # Cannogabang
        
        # Dark Heroes
        28: "https://ejemplo.com/ravenous.png",    # Ravenous
        29: "https://ejemplo.com/sonarchy.png",    # Sonarchy
        30: "https://ejemplo.com/ragewolf.png",    # Ragewolf
        31: "https://ejemplo.com/naughtyfins.png", # Naughtyfins
        32: "https://ejemplo.com/slogturtle.png",  # Slogturtle
        33: "https://ejemplo.com/covet-hiss.png",  # Covet-Hiss
        34: "https://ejemplo.com/buzzcrave.png",   # Buzzcrave
    }
    
    # Imagen por defecto si no se encuentra la clase
    default_image = "https://cdn.discordapp.com/app-icons/1348020517088530523/04c7c322375d150d2242b8d032f19259.png?size=32"
    
    # Retornar la imagen correspondiente o la imagen por defecto si no se encuentra
    return hero_images.get(class_id, default_image)


# Imagen para modo sigilo (enfrentamiento PvP)
STEALTH_IMAGE = "https://cdn.glitch.global/4b441d69-bc50-4b7e-a66d-e773275e1030/vs.jpg?v=1741511997545"


if __name__ == "__main__":
    print("Iniciando el programa de Rich Presence para Patapon en PPSSPP...")
    
    # Intentar conectar con Discord
    client_id = "1348020517088530523"
    try:
        RPC = Presence(client_id)
        RPC.connect()
        print("Conectado a Discord Rich Presence")
    except Exception as e:
        print(f"Error al conectar con Discord: {e}")
        RPC = None
    
    try:
        game_data = get_game_data()
        if game_data:
            detail, state = process_game_data(game_data)
            print(f"Estado inicial: {detail} | {state}")
        else:
            detail, state = "Esperando juego...", None
            
        # Archivo de registro para depuración
        log_file = "memory_log.txt"
        print(f"Registrando datos en {log_file}")
        
        while True:
            if RPC:
                # Verificar si estamos en modo sigilo (enfrentamiento)
                if game_data and game_data.get("stealth_mode", False):
                    # Usar imágenes genéricas para el modo de enfrentamiento
                    large_image = "https://pbs.twimg.com/media/GliyDAkbUAAEzZb?format=png&name=small"  # Mantener la imagen principal
                    small_image = STEALTH_IMAGE  # Imagen genérica para ocultar la clase
                    small_text = "Modo enfrentamiento"
                    print("Usando modo de sigilo para ocultar información de clase")
                else:
                    # Usar imágenes normales fuera del modo sigilo
                    large_image = "https://pbs.twimg.com/media/GliyDAkbUAAEzZb?format=png&name=small"
                    
                    # Seleccionar imagen pequeña según la clase actual del jugador
                    if game_data and "current_class_id" in game_data:
                        current_class_id = game_data["current_class_id"]
                        small_image = get_hero_image(current_class_id)
                        small_text = game_data.get("current_class", "Patapon")
                        print(f"Usando imagen de héroe normal: {small_image} para clase: {game_data.get('current_class', 'Desconocida')} (ID: {current_class_id})")
                    else:
                        # Imagen por defecto si no hay información de clase
                        small_image = "https://cdn.discordapp.com/app-icons/1348020517088530523/04c7c322375d150d2242b8d032f19259.png?size=32"
                        small_text = "Patapon"
                
                RPC.update(
                    details=detail,
                    state=state,
                    large_image=large_image,
                    small_image=small_image,
                    small_text=small_text
                )
            
            time.sleep(5)
            
            # Obtener nuevos datos
            game_data = get_game_data()
            if game_data:
                detail, state = process_game_data(game_data)
                
                # Guardar datos en archivo de registro (omitir en modo sigilo para más seguridad)
                if not game_data.get("stealth_mode", False):
                    with open(log_file, "a", encoding="utf-8") as f:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"\n\n=== {timestamp} ===\n")
                        for key, value in game_data.items():
                            f.write(f"{key}: {value}\n")
                else:
                    # Solo registrar que estamos en modo sigilo, sin detalles
                    with open(log_file, "a", encoding="utf-8") as f:
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"\n\n=== {timestamp} ===\n")
                        f.write("Modo sigilo activado - Datos ocultos\n")
            else:
                detail, state = "Esperando juego...", None
                
    except KeyboardInterrupt:
        print("\nPrograma terminado por el usuario")
    except Exception as e:
        print(f"Error: {e}")