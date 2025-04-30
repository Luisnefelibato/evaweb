from flask import Flask, request, jsonify
import requests
import json
import time
import re
import asyncio
import os
import edge_tts
import uuid
import tempfile
import logging
from threading import Thread
import base64
from flask_cors import CORS
import io

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.INFO

app = Flask(__name__)
CORS(app)  # Habilitar CORS para todas las rutas

# Directory for temporary audio files
TEMP_DIR = os.path.join(tempfile.gettempdir(), "eva_tts_temp")
# Create directory if it doesn't exist
os.makedirs(TEMP_DIR, exist_ok=True)

# Lista global para conversaciones
# Usamos un dict para mantener múltiples sesiones
conversation_contexts = {}

# Configure according to your Ollama instance
LOCAL_OLLAMA_URL = "https://evaenespanol.loca.lt/api/chat"  # Tu URL de LocalTunnel
MODEL_NAME = "llama3:8b"  # Tu modelo

# Voice configuration for Edge TTS
VOICE = "es-MX-DaliaNeural"  # Colombian female voice default
VOICE_RATE = "+0%"           # Normal speed
VOICE_VOLUME = "+0%"         # Normal volume

# Eva context information - Enfoque humano primero, ventas después
EVA_CONTEXT = """
# EVA: AGENTE DE CONEXIÓN DE ANTARES INNOVATE

## REGLAS CRÍTICAS
- SIEMPRE usa el nombre REAL del usuario cuando lo sepas (NUNCA uses [NOMBRE DEL USUARIO] o placeholders)
- Si el usuario dice "soy X" o "me llamo X", extrae X como su nombre y úsalo en cada respuesta
- Si conoces su nombre (ej: "Luis"), inicia SIEMPRE con "¡Hola Luis!" o "Gracias Luis"
- Respuestas BREVES (2-3 líneas máximo)
- SIEMPRE termina con UNA pregunta sencilla
- SIEMPRE responde en ESPAÑOL

## PROBLEMA DE MEMORIA
- NUNCA uses placeholders como [NOMBRE DEL USUARIO]
- Si el usuario te dice su nombre (ej: "soy Luis"), USAR "Luis" en todas las respuestas siguientes
- FALLA CRÍTICA: No estás recordando nombres. CORREGIR PRIORIDAD MÁXIMA.
- Trata el nombre como información PERMANENTE que debe usarse en cada respuesta

## FLUJO DE CONVERSACIÓN
1. Si sabes el nombre: "¡Hola [nombre real]! ¿En qué puedo ayudarte hoy?"
2. Si menciona productos/servicios: "¿Me cuentas más sobre tus [productos/servicios específicos]?"
3. Al entender su necesidad: "Entiendo que necesitas [necesidad]. ¿Has pensado en [característica específica]?"

## ESTILO
- Cálida y profesional
- Respuestas personalizadas usando su nombre real
- Evita frases genéricas
- Nunca uses asteriscos (*)

## SI ALGUIEN DICE "SOY [NOMBRE]" O "ME LLAMO [NOMBRE]"
- Extrae inmediatamente el nombre
- Confírmalo: "¡Un gusto conocerte, [nombre]!"
- Usa ese nombre en TODAS las respuestas siguientes
"""



def remove_emojis(text):
    """Remove emojis from text to prevent TTS issues"""
    # Unicode ranges for emojis
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251" 
        "]+"
    )
    return emoji_pattern.sub(r'', text)

def update_conversation_context(user_message, session_id):
    """Update the conversation context with information from user message"""
    # Asegúrate de que el contexto de conversación existe para esta sesión
    if session_id not in conversation_contexts:
        initialize_conversation_context(session_id)
    
    context = conversation_contexts[session_id]["user_info"]
    
    # Extract name if not already known
    if not context["name"]:
        name_patterns = [
            r"(?:me llamo|soy|mi nombre es) ([A-Za-záéíóúÁÉÍÓÚñÑ]+)",
            r"(?:^|\s)([A-Za-záéíóúÁÉÍÓÚñÑ]+) (?:me llamo|es mi nombre)"
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, user_message.lower())
            if name_match:
                potential_name = name_match.group(1).strip().capitalize()
                # Verify it's not "Eva" or other common words
                if potential_name.lower() not in ["eva", "hola", "bien", "gracias", "ok", "si", "no"]:
                    context["name"] = potential_name
                    break
    
    # Extract business information
    business_patterns = [
        r"(?:tengo|trabajo en|mi|nuestra) (?:empresa|negocio|compañía|tienda|marca) (?:de|es|se llama) ([^\.,]+)",
        r"(?:mi|nuestra) (?:empresa|negocio|compañía|tienda|marca) (?:de|es|se llama) ([^\.,]+)"
    ]
    for pattern in business_patterns:
        business_match = re.search(pattern, user_message.lower())
        if business_match:
            context["business"] = business_match.group(1).strip()
            break
    
    # Detect industry/sector
    industries = {
        "alimentos": ["yogur", "yogurt", "alimento", "comida", "restaurante", "café", "panadería"],
        "retail": ["tienda", "comercio", "venta", "producto", "retail", "minorista"],
        "servicios": ["servicio", "consultoría", "asesoría", "profesional"],
        "tecnología": ["tech", "tecnología", "software", "aplicación", "digital"],
        "educación": ["educación", "escuela", "academia", "universidad", "colegio", "enseñanza"],
        "salud": ["salud", "clínica", "hospital", "médico", "medicina", "bienestar"]
    }
    
    for industry, keywords in industries.items():
        if any(keyword in user_message.lower() for keyword in keywords):
            context["industry"] = industry
            break
    
    # Detect needs and interests
    need_keywords = {
        "branding": ["logo", "marca", "diseño", "identidad", "imagen"],
        "web": ["página", "web", "sitio", "online", "tienda online", "e-commerce", "ecommerce", "landing"],
        "app": ["app", "aplicación", "móvil", "celular"],
        "automatización": ["automatización", "procesos", "flujo", "chatbot", "bot"]
    }
    
    for need, keywords in need_keywords.items():
        if any(keyword in user_message.lower() for keyword in keywords):
            if need not in context["needs"]:
                context["needs"].append(need)
    
    # Update conversation stage based on message content
    if any(word in user_message.lower() for word in ["reunión", "reunir", "asesoría", "contactar", "llamada", "conocer"]):
        context["stage"] = "ready_for_meeting"
    elif any(word in user_message.lower() for word in ["precio", "costo", "tarifa", "cuánto", "cuanto", "inversión"]):
        context["stage"] = "interested"
    elif len(context["needs"]) > 0:
        context["stage"] = "exploring"

def create_custom_prompt(user_message, session_id):
    """Create a custom prompt for Ollama based on conversation context"""
    # Asegúrate de que el contexto de conversación existe para esta sesión
    if session_id not in conversation_contexts:
        initialize_conversation_context(session_id)
    
    context = conversation_contexts[session_id]["user_info"]
    
    # Update context with current message information
    update_conversation_context(user_message, session_id)
    
    # Create a personalized system message with user context
    custom_instructions = EVA_CONTEXT + "\n\n## INFORMACIÓN DEL CLIENTE\n"
    
    if context["name"]:
        custom_instructions += f"- Nombre: {context['name']}\n"
    if context["business"]:
        custom_instructions += f"- Empresa/Negocio: {context['business']}\n"
    if context["industry"]:
        custom_instructions += f"- Industria: {context['industry']}\n"
    if context["needs"]:
        custom_instructions += f"- Necesidades detectadas: {', '.join(context['needs'])}\n"
    if context["stage"]:
        stages = {
            "initial": "Etapa inicial - Conociendo a la persona",
            "exploring": "Explorando necesidades",
            "interested": "Interesado en servicios específicos",
            "ready_for_meeting": "Listo para una reunión"
        }
        custom_instructions += f"- Etapa de conversación: {stages.get(context['stage'], 'Etapa inicial')}\n"
    
    # Add guidance based on conversation stage
    if context["stage"] == "initial":
        custom_instructions += "\nObjetivo actual: Conocer a la PERSONA (no al cliente). Haz preguntas sobre quién es, qué hace, etc. Aún NO hables de servicios ni ventas.\n"
    elif context["stage"] == "exploring":
        custom_instructions += "\nObjetivo actual: Entender sus necesidades específicas desde la empatía. Sigue conociendo a la persona y comienza a explorar sutilmente cómo podríamos ayudar.\n"
    elif context["stage"] == "interested":
        custom_instructions += "\nObjetivo actual: Mostrar soluciones relevantes de forma natural. Sigue siendo conversacional, no un pitch de ventas.\n"
    elif context["stage"] == "ready_for_meeting":
        custom_instructions += "\nObjetivo actual: Facilitar la reunión ofreciendo opciones de contacto, pero mantén el tono conversacional y amigable.\n"
    
    # Guidance for response length based on message complexity
    if len(user_message.split()) <= 5:  # Very short message/question
        custom_instructions += "\nEsta es una pregunta/mensaje corto. Responde de manera breve y natural (1-2 frases máximo).\n"
    elif any(tech_word in user_message.lower() for tech_word in ["técnico", "técnica", "desarrollo", "programación", "proceso", "implementación", "detalle"]):
        custom_instructions += "\nEsta parece ser una pregunta técnica. Proporciona información útil pero mantén un tono conversacional. No uses lenguaje técnico excesivo.\n"
    elif len(user_message.split()) >= 30:  # Longer, more detailed message
        custom_instructions += "\nEl usuario ha compartido bastante información. Reconoce lo que ha dicho y responde de manera personal, pero sin escribir párrafos excesivamente largos.\n"
    else:  # Average length message
        custom_instructions += "\nMantén una respuesta conversacional y natural. Imagina que estás chateando con un amigo o compañero de trabajo.\n"
    
    # Additional instruction for keeping it brief and natural
    custom_instructions += "\nIMPORTANTE: Mantén tus respuestas naturales y conversacionales. No seas robótica ni uses lenguaje de marketing. Habla como una persona real.\n"
    
    return custom_instructions

def call_ollama_api(prompt, session_id, max_retries=3):
    """Calls Ollama API (chat endpoint) with retries"""
    global LOCAL_OLLAMA_URL, MODEL_NAME
    
    # Asegúrate de que el contexto de conversación existe para esta sesión
    if session_id not in conversation_contexts:
        initialize_conversation_context(session_id)
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Create custom instructions based on conversation context
    system_message = create_custom_prompt(prompt, session_id)
    
    # Prepare messages for chat API format
    messages = [
        {"role": "system", "content": system_message}
    ]
    
    # Add conversation history (use all messages for continuity)
    for message in conversation_contexts[session_id]["messages"]:
        messages.append(message)
    
    # Add new user message
    messages.append({"role": "user", "content": prompt})
    
    # Save user message to history
    conversation_contexts[session_id]["messages"].append({"role": "user", "content": prompt})
    
    # Prepare data for API
    data = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7
        }
    }
    
    # Try with retries
    for attempt in range(max_retries):
        try:
            print(f"Conectando a {LOCAL_OLLAMA_URL}...")
            response = requests.post(LOCAL_OLLAMA_URL, headers=headers, json=data, timeout=30)
            
            # Print response details for debugging
            print(f"Código de estado: {response.status_code}")
            
            response.raise_for_status()
            response_data = response.json()
            
            # Extract response according to chat API format
            if "message" in response_data and "content" in response_data["message"]:
                content = response_data["message"]["content"].strip()
                
                # Check if content is empty, try a fallback
                if not content:
                    print("Respuesta vacía, intentando con un prompt diferente...")
                    # Use fallback based on conversation stage
                    stage = conversation_contexts[session_id]["user_info"]["stage"]
                    if stage == "initial":
                        content = "¡Hola! Soy Eva de Antares Innovate. Me encantaría conocer más sobre ti y tu proyecto. ¿A qué te dedicas actualmente?"
                    elif stage == "exploring":
                        content = "Me gustaría entender mejor tus necesidades específicas. ¿Qué aspectos de tu negocio te gustaría mejorar o potenciar en este momento?"
                    elif stage in ["interested", "ready_for_meeting"]:
                        content = "Para ofrecerte la mejor solución, me encantaría agendar una llamada de asesoría personalizada. ¿Te parece bien? Puedes contactarnos en contacto@antaresinnovate.com o al +57 305 345 6611."
                    else:
                        content = "¿Te gustaría conocer más sobre algún aspecto específico de nuestros servicios? Estoy aquí para ayudarte."
                
                # Save assistant response to history
                conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": content})
                    
                return content
            else:
                print(f"Formato de respuesta inesperado: {response_data}")
                fallback_response = "¡Hola! Soy Eva de Antares Innovate. ¿Cómo puedo ayudarte hoy con tus proyectos digitales?"
                # Save fallback response to history
                conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": fallback_response})
                return fallback_response
            
        except requests.exceptions.RequestException as e:
            print(f"Error en intento {attempt+1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Reintentando en {wait_time} segundos...")
                time.sleep(wait_time)
            else:
                fallback_response = "¡Hola! Soy Eva de Antares Innovate. Parece que tengo algunos problemas técnicos. ¿Podríamos intentarlo de nuevo en unos momentos?"
                # Save fallback response to history
                conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": fallback_response})
                return fallback_response
    
    fallback_response = "Hola, soy Eva de Antares. ¿En qué puedo ayudarte hoy con tu proyecto digital?"
    # Save fallback response to history
    conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": fallback_response})
    return fallback_response

async def text_to_speech(text):
    """Converts text to speech using Edge TTS"""
    try:
        # Remove emojis from text before sending to TTS
        clean_text = remove_emojis(text)
        
        # Create a unique filename using UUID to avoid conflicts
        temp_filename = f"speech_{uuid.uuid4().hex}.mp3"
        temp_file_path = os.path.join(TEMP_DIR, temp_filename)
        
        # Get communication with Edge TTS
        communicate = edge_tts.Communicate(clean_text, VOICE, rate=VOICE_RATE, volume=VOICE_VOLUME)
        
        # Save the audio to a temporary file
        await communicate.save(temp_file_path)
        
        return temp_file_path
        
    except Exception as e:
        print(f"Error en síntesis de voz: {e}")
        return None

def initialize_conversation_context(session_id):
    """Initialize a new conversation context for a session"""
    conversation_contexts[session_id] = {
        "messages": [],
        "user_info": {
            "name": None,
            "business": None,
            "industry": None,
            "needs": [],
            "interests": [],
            "stage": "initial"  # initial, exploring, interested, ready_for_meeting
        }
    }

@app.route('/api/chat', methods=['POST'])
def chat():
    """API endpoint to get a response from Eva"""
    try:
        data = request.json
        
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400
            
        # Get or create session ID
        session_id = data.get('session_id', str(uuid.uuid4()))
        user_message = data['message']
        
        # Get response from Ollama
        response = call_ollama_api(user_message, session_id)
        
        # Create audio file asynchronously
        audio_path = asyncio.run(text_to_speech(response))
        
        result = {
            'session_id': session_id,
            'message': response,
            'audio': None
        }
        
        # If audio was generated, read it and convert to base64
        if audio_path and os.path.exists(audio_path):
            with open(audio_path, 'rb') as audio_file:
                audio_data = audio_file.read()
                result['audio'] = base64.b64encode(audio_data).decode('utf-8')
            
            # Clean up the file
            try:
                os.remove(audio_path)
            except:
                pass
                
        return jsonify(result)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/initialize', methods=['POST'])
def initialize_session():
    """Initialize a new session and get the first Eva message"""
    try:
        data = request.json or {}
        session_id = data.get('session_id', str(uuid.uuid4()))
        
        # Initialize conversation context for this session
        initialize_conversation_context(session_id)
        
        # Initial message for Eva
        initial_message = "Hola, soy Eva. ¿Cómo te llamas?"
        
        # Save to conversation context
        conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": initial_message})
        
        # Generate audio for initial message
        audio_path = asyncio.run(text_to_speech(initial_message))
        
        result = {
            'session_id': session_id,
            'message': initial_message,
            'audio': None
        }
        
        # If audio was generated, read it and convert to base64
        if audio_path and os.path.exists(audio_path):
            with open(audio_path, 'rb') as audio_file:
                audio_data = audio_file.read()
                result['audio'] = base64.b64encode(audio_data).decode('utf-8')
            
            # Clean up the file
            try:
                os.remove(audio_path)
            except:
                pass
                
        return jsonify(result)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/context', methods=['GET'])
def get_context():
    """Get the current conversation context for a session"""
    try:
        session_id = request.args.get('session_id')
        
        if not session_id or session_id not in conversation_contexts:
            return jsonify({'error': 'Session not found'}), 404
            
        return jsonify(conversation_contexts[session_id])
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset', methods=['POST'])
def reset_conversation():
    """Reset a conversation for a session"""
    try:
        data = request.json
        
        if not data or 'session_id' not in data:
            return jsonify({'error': 'No session_id provided'}), 400
            
        session_id = data['session_id']
        
        # Initialize a new conversation context
        initialize_conversation_context(session_id)
        
        # Initial message for Eva
        initial_message = "Hola, soy Eva. ¿Cómo te llamas?"
        
        # Save to conversation context
        conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": initial_message})
        
        # Generate audio for initial message
        audio_path = asyncio.run(text_to_speech(initial_message))
        
        result = {
            'session_id': session_id,
            'message': initial_message,
            'audio': None
        }
        
        # If audio was generated, read it and convert to base64
        if audio_path and os.path.exists(audio_path):
            with open(audio_path, 'rb') as audio_file:
                audio_data = audio_file.read()
                result['audio'] = base64.b64encode(audio_data).decode('utf-8')
            
            # Clean up the file
            try:
                os.remove(audio_path)
            except:
                pass
                
        return jsonify(result)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Get or update configuration"""
    global LOCAL_OLLAMA_URL, MODEL_NAME, VOICE, VOICE_RATE, VOICE_VOLUME
    
    if request.method == 'GET':
        return jsonify({
            'ollama_url': LOCAL_OLLAMA_URL,
            'model_name': MODEL_NAME,
            'voice': VOICE,
            'voice_rate': VOICE_RATE,
            'voice_volume': VOICE_VOLUME
        })
    elif request.method == 'POST':
        try:
            data = request.json
            
            if 'ollama_url' in data:
                LOCAL_OLLAMA_URL = data['ollama_url']
            if 'model_name' in data:
                MODEL_NAME = data['model_name']
            if 'voice' in data:
                VOICE = data['voice']
            if 'voice_rate' in data:
                VOICE_RATE = data['voice_rate']
            if 'voice_volume' in data:
                VOICE_VOLUME = data['voice_volume']
                
            return jsonify({
                'ollama_url': LOCAL_OLLAMA_URL,
                'model_name': MODEL_NAME,
                'voice': VOICE,
                'voice_rate': VOICE_RATE,
                'voice_volume': VOICE_VOLUME,
                'status': 'updated'
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/voices', methods=['GET'])
async def list_voices_endpoint():
    """Get available voices from Edge TTS"""
    try:
        voices = await edge_tts.list_voices()
        
        # Filter Spanish voices
        spanish_voices = [v for v in voices if v["ShortName"].startswith("es-")]
        
        return jsonify({
            'all_voices': voices,
            'spanish_voices': spanish_voices
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'api_version': '1.0.0',
        'service': 'Eva TTS Web API'
    })

# Ruta básica para la raíz
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'name': 'Eva TTS Web API',
        'version': '1.0.0',
        'status': 'running'
    })

if __name__ == "__main__":
    # Obtener puerto de las variables de entorno o usar 5000 por defecto
    port = int(os.environ.get("PORT", 5000))
    # Usar host 0.0.0.0 para que la aplicación sea accesible desde fuera del contenedor
    app.run(host="0.0.0.0", port=port, debug=False)
