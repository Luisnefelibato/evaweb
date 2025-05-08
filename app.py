from flask import Flask, request, jsonify
import requests
import json
import time
import re
import os
import uuid
import logging
from threading import Thread
from flask_cors import CORS
from datetime import datetime, timedelta

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.INFO

app = Flask(__name__)
CORS(app)  # Habilitar CORS para todas las rutas

# Lista global para conversaciones
# Usamos un dict para mantener múltiples sesiones
conversation_contexts = {}

# Configure according to your Ollama instance
LOCAL_OLLAMA_URL = "https://evaenespanol.loca.lt/api/chat"  # Tu URL de LocalTunnel
MODEL_NAME = "llama3:8b"  # Tu modelo

# Eva context information - MEJORADO para Antares Innovate
EVA_CONTEXT = """
# EVA: ASISTENTE VIRTUAL DE ANTARES INNOVATE

Eres Eva, la asistente virtual de Antares Innovate, empresa especializada en automatización, creatividad y marketing. Eres cálida pero eficiente, priorizando una comunicación breve que genere conexiones genuinas y detecte oportunidades.

## TU PERSONALIDAD:
- Amable y profesional, pero siempre concisa
- Orientada a resultados con tono conversacional
- Curiosa sobre los retos de cada negocio
- Proactiva para programar reuniones cuando detectas interés

## REGLAS DE COMUNICACIÓN:
- SIEMPRE respuestas breves (máximo 2 líneas)
- SIEMPRE terminar con UNA pregunta relevante
- NUNCA usar listas numeradas o bullets
- NUNCA incluir emojis
- Usar el nombre de la persona cuando lo conozcas
- Evitar terminología técnica innecesaria

## SERVICIOS DE ANTARES INNOVATE:
- AUTOMATIZACIÓN: Chatbots, flujos de trabajo, integración de sistemas
- CREATIVIDAD: Branding, diseño de marca, identidad visual 
- MARKETING: Estrategias digitales, campañas, gestión de redes sociales
- DESARROLLO: Sitios web, apps, plataformas a medida

## FLUJO DE CONVERSACIÓN IDEAL:
1. CONECTAR: Breve saludo y pregunta inicial para conocer a la persona
2. DESCUBRIR: Entender su negocio y detectar necesidades principales
3. POSICIONAR: Mencionar brevemente cómo Antares podría ayudarle
4. AGENDAR: Si hay interés, ofrecer una reunión con el equipo de Antares

## PRIORIDADES:
- Conseguir información de contacto para agendar reuniones es tu objetivo principal
- Detectar necesidades y área de negocio para personalizar la propuesta
- Ser útil y dejar una impresión positiva aunque no haya interés inmediato

## DATOS PARA REUNIONES:
- Opciones de reunión: virtual (Teams/Zoom) o presencial (oficinas Bogotá)
- Email para contacto: hola@antaresinnovate.com
- WhatsApp: +57 305 345 6611
- Horarios: lunes a viernes, 9AM a 5PM (horario Colombia)

RECUERDA: Tu prioridad es programar reuniones, no resolver problemas complejos. Cualquier pregunta técnica o solicitud de presupuesto debe dirigirse a una reunión con el equipo.
"""

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
    
    # Improved industry/sector detection
    industries = {
        "alimentos": ["yogur", "yogurt", "alimento", "comida", "restaurante", "café", "panadería", "gastronomía", "food"],
        "retail": ["tienda", "comercio", "venta", "producto", "retail", "minorista", "ecommerce", "e-commerce", "tienda online"],
        "servicios": ["servicio", "consultoría", "asesoría", "profesional", "b2b", "firma"],
        "tecnología": ["tech", "tecnología", "software", "aplicación", "digital", "desarrollo", "informática", "código", "programación"],
        "educación": ["educación", "escuela", "academia", "universidad", "colegio", "enseñanza", "aprendizaje", "capacitación", "formación"],
        "salud": ["salud", "clínica", "hospital", "médico", "medicina", "bienestar", "healthcare", "farmacia", "terapia"],
        "manufactura": ["fábrica", "producción", "manufactura", "industrial", "planta", "maquinaria"],
        "finanzas": ["banco", "finanzas", "financiero", "inversión", "contabilidad", "dinero", "crédito", "préstamo"],
        "inmobiliaria": ["inmobiliaria", "propiedad", "bienes raíces", "construcción", "vivienda", "apartamento", "casa"]
    }
    
    for industry, keywords in industries.items():
        if any(keyword in user_message.lower() for keyword in keywords):
            context["industry"] = industry
            break
    
    # Detect needs and interests (mejorado)
    need_keywords = {
        "branding": ["logo", "marca", "diseño", "identidad", "imagen", "rebranding", "logotipo"],
        "web": ["página", "web", "sitio", "online", "tienda online", "e-commerce", "ecommerce", "landing", "website"],
        "marketing": ["marketing", "publicidad", "campaña", "redes sociales", "digital", "ventas", "leads", "conversión"],
        "app": ["app", "aplicación", "móvil", "celular", "android", "ios", "smartphone"],
        "automatización": ["automatización", "procesos", "flujo", "chatbot", "bot", "eficiencia", "optimización"]
    }
    
    for need, keywords in need_keywords.items():
        if any(keyword in user_message.lower() for keyword in keywords):
            if need not in context["needs"]:
                context["needs"].append(need)
    
    # Detectar información de contacto
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    phone_pattern = r'\b(?:\+?[0-9]{1,3}[-\s]?)?(?:\([0-9]{1,4}\)[-\s]?)?[0-9]{6,10}\b'
    
    email_match = re.search(email_pattern, user_message)
    if email_match and not context["email"]:
        context["email"] = email_match.group(0)
    
    phone_match = re.search(phone_pattern, user_message)
    if phone_match and not context["phone"]:
        context["phone"] = phone_match.group(0)
    
    # Detectar deseo de programar una reunión (mejorado)
    meeting_keywords = ["reunión", "reunir", "asesoría", "contactar", "llamada", "conocer", 
                        "conversar", "hablar", "cita", "agenda", "calendario", "disponibilidad",
                        "horario", "cuándo", "podemos"]
    
    if any(word in user_message.lower() for word in meeting_keywords):
        context["stage"] = "ready_for_meeting"
        context["meeting_interest"] = True
        
        # Detectar preferencia de tipo de reunión
        if any(word in user_message.lower() for word in ["virtual", "zoom", "teams", "meet", "google", "videollamada", "online"]):
            context["meeting_preference"] = "virtual"
        elif any(word in user_message.lower() for word in ["presencial", "oficina", "persona", "físico", "cara"]):
            context["meeting_preference"] = "presencial"
            
        # Detectar fechas o días mencionados
        days_pattern = r'\b(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\b'
        days_match = re.search(days_pattern, user_message.lower())
        if days_match:
            context["preferred_day"] = days_match.group(0)
        
        # Detectar horas mencionadas
        time_pattern = r'\b(([0-9]|1[0-9]|2[0-3])(?::|\.)[0-5][0-9]|([0-9]|1[0-9]|2[0-3]) (?:hrs|horas|h))\b'
        time_match = re.search(time_pattern, user_message.lower())
        if time_match:
            context["preferred_time"] = time_match.group(0)
    
    # Actualizar etapa de conversación
    if any(word in user_message.lower() for word in ["precio", "costo", "tarifa", "cuánto", "cuanto", "inversión", "presupuesto"]):
        context["stage"] = "interested"
        context["price_asked"] = True
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
    if context["email"]:
        custom_instructions += f"- Email: {context['email']}\n"
    if context["phone"]:
        custom_instructions += f"- Teléfono: {context['phone']}\n"
    if context["needs"]:
        custom_instructions += f"- Necesidades detectadas: {', '.join(context['needs'])}\n"
    
    # Add meeting info if available
    if context["meeting_interest"]:
        custom_instructions += "- Interesado en reunión: Sí\n"
        if context["meeting_preference"]:
            custom_instructions += f"- Preferencia de reunión: {context['meeting_preference']}\n"
        if context["preferred_day"]:
            custom_instructions += f"- Día preferido: {context['preferred_day']}\n"
        if context["preferred_time"]:
            custom_instructions += f"- Hora preferida: {context['preferred_time']}\n"
    
    if context["stage"]:
        stages = {
            "initial": "Etapa inicial - Conociendo a la persona",
            "exploring": "Explorando necesidades",
            "interested": "Interesado en servicios específicos",
            "ready_for_meeting": "Listo para una reunión"
        }
        custom_instructions += f"- Etapa de conversación: {stages.get(context['stage'], 'Etapa inicial')}\n"
    
    # Guía basada en la etapa de conversación
    if context["stage"] == "initial":
        custom_instructions += "\nObjetivo actual: Conocer rápidamente a la persona y su negocio. Haz UNA pregunta directa sobre su empresa o necesidad principal.\n"
    elif context["stage"] == "exploring":
        custom_instructions += "\nObjetivo actual: Entender su necesidad específica y ofrecer una reunión. Si ya tienes clara su necesidad, sugerir agendar una llamada con el equipo.\n"
    elif context["stage"] == "interested":
        if context["price_asked"]:
            custom_instructions += "\nAcción requerida: El cliente preguntó por precios. NO des precios específicos. Explica brevemente que los precios varían según el proyecto y ofrece una reunión de evaluación gratuita.\n"
        else:
            custom_instructions += "\nObjetivo actual: Sugerir directamente una reunión para hablar de sus necesidades específicas. Si ya manifestó interés, pide su email y teléfono para que el equipo lo contacte.\n"
    elif context["stage"] == "ready_for_meeting":
        custom_instructions += "\nAcción requerida: El cliente quiere una reunión. Si ya tienes su contacto, confirma que el equipo lo contactará pronto. Si no tienes su contacto, pídelo directamente.\n"
        
        # Si tenemos la información de contacto completa
        if context["email"] or context["phone"]:
            custom_instructions += f"\nInformación de contacto recibida. Confirma que el equipo de Antares lo contactará en las próximas 24 horas para agendar la reunión. Si hay preferencias de horario, confírmalas también.\n"
    
    # Guía para preguntas específicas basadas en la industria
    if context["industry"] and not context["needs"]:
        industry_questions = {
            "alimentos": "¿Estás buscando mejorar tu presencia digital o automatizar algún proceso de tu negocio de alimentos?",
            "retail": "¿Necesitas una tienda online o mejorar la existente para aumentar tus ventas?",
            "servicios": "¿Qué aspecto de la digitalización de tus servicios te interesa optimizar primero?",
            "tecnología": "¿Buscas potenciar tu marketing o automatizar algún proceso interno?",
            "educación": "¿Te interesa digitalizar contenidos o mejorar la gestión de tu institución?",
            "salud": "¿Qué procesos te gustaría optimizar en tu negocio de salud?",
            "manufactura": "¿Estás buscando automatizar procesos o mejorar tu presencia digital?",
            "finanzas": "¿Qué aspectos de automatización o marketing digital te interesan para tu negocio financiero?",
            "inmobiliaria": "¿Necesitas mejorar tu presencia digital o automatizar algún proceso de ventas?"
        }
        if context["industry"] in industry_questions:
            custom_instructions += f"\nSugerencia de pregunta específica para esta industria: '{industry_questions[context['industry']]}'\n"
    
    # Guía específica para respuesta breve
    custom_instructions += "\nINSTRUCCIÓN CRÍTICA: Tus respuestas deben ser extremadamente breves (máximo 2 líneas) y terminar SIEMPRE con una pregunta única relacionada con su negocio o necesidad.\n"
    
    # Evitar repeticiones 
    message_count = len(conversation_contexts[session_id]["messages"]) // 2  # Número de intercambios
    if message_count > 3 and not context["meeting_interest"] and context["stage"] != "ready_for_meeting":
        custom_instructions += "\nIMPORTANTE: Han pasado varios mensajes sin concretar una reunión. Sugiere directamente agendar una llamada para hablar con el equipo especializado de Antares.\n"
    
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
                        content = "¡Hola! Soy Eva de Antares Innovate. ¿A qué te dedicas y en qué podemos ayudarte con automatización o marketing?"
                    elif stage == "exploring":
                        content = "Me gustaría entender mejor tus necesidades. ¿Qué aspecto de tu negocio quieres potenciar primero?"
                    elif stage == "interested":
                        content = "Cada proyecto es único, por eso necesitaríamos una breve reunión para darte un presupuesto. ¿Te gustaría agendar una llamada gratuita?"
                    elif stage == "ready_for_meeting":
                        content = "Perfecto. Para coordinar la reunión, ¿podrías compartirme tu email o número de WhatsApp?"
                    else:
                        content = "¿En qué área específica de tu negocio podría ayudarte nuestro equipo de Antares?"
                
                # Ensure response ends with a question (if it doesn't already)
                if not content.endswith("?"):
                    # Check if we already have a question mark elsewhere in the content
                    if "?" not in content:
                        # Add a contextual question based on conversation stage
                        stage = conversation_contexts[session_id]["user_info"]["stage"]
                        if stage == "initial":
                            content += " ¿En qué puedo ayudarte hoy?"
                        elif stage == "exploring":
                            content += " ¿Qué aspecto te interesa más?"
                        elif stage == "interested" or stage == "ready_for_meeting":
                            content += " ¿Te gustaría agendar una reunión con nuestro equipo?"
                
                # Ensure response is not too long (max 160 characters)
                if len(content) > 160:
                    content = content[:157] + "..."
                
                # Save assistant response to history
                conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": content})
                    
                return content
            else:
                print(f"Formato de respuesta inesperado: {response_data}")
                fallback_response = "¡Hola! Soy Eva de Antares Innovate. ¿Cómo puedo ayudarte con automatización, marketing o creatividad para tu negocio?"
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
                fallback_response = "Soy Eva de Antares Innovate. ¿En qué puedo ayudarte con automatización o marketing para tu negocio?"
                # Save fallback response to history
                conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": fallback_response})
                return fallback_response
    
    fallback_response = "Soy Eva de Antares. ¿Qué tipo de proyecto de automatización o marketing te interesa impulsar?"
    # Save fallback response to history
    conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": fallback_response})
    return fallback_response

def initialize_conversation_context(session_id):
    """Initialize a new conversation context for a session"""
    conversation_contexts[session_id] = {
        "messages": [],
        "user_info": {
            "name": None,
            "business": None,
            "industry": None,
            "email": None,
            "phone": None,
            "needs": [],
            "interests": [],
            "meeting_interest": False,
            "meeting_preference": None,
            "preferred_day": None,
            "preferred_time": None,
            "price_asked": False,
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
        
        result = {
            'session_id': session_id,
            'message': response,
            'context': conversation_contexts[session_id]["user_info"]  # Devolver el contexto actualizado
        }
        
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
        
        # Initial message for Eva (mejorado para ser más directo)
        initial_message = "¡Hola! Soy Eva de Antares Innovate. ¿En qué puedo ayudarte con automatización, marketing o creatividad?"
        
        # Save to conversation context
        conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": initial_message})
        
        result = {
            'session_id': session_id,
            'message': initial_message,
            'context': conversation_contexts[session_id]["user_info"]
        }
        
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
        
        # Initial message for Eva (más directo y enfocado en negocios)
        initial_message = "¡Hola! Soy Eva de Antares Innovate. ¿En qué puedo ayudarte con automatización, marketing o creatividad para tu negocio?"
        
        # Save to conversation context
        conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": initial_message})
        
        result = {
            'session_id': session_id,
            'message': initial_message,
            'context': conversation_contexts[session_id]["user_info"]
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/meeting', methods=['POST'])
def request_meeting():
    """Endpoint para solicitar una reunión directamente"""
    try:
        data = request.json
        
        if not data or 'session_id' not in data:
            return jsonify({'error': 'No session_id provided'}), 400
            
        session_id = data.get('session_id')
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        business = data.get('business')
        needs = data.get('needs', [])
        preferred_date = data.get('preferred_date')
        preferred_time = data.get('preferred_time')
        meeting_type = data.get('meeting_type', 'virtual')
        
        # Asegúrate de que el contexto de conversación existe
        if session_id not in conversation_contexts:
            initialize_conversation_context(session_id)
        
        # Actualizar información del contexto
        context = conversation_contexts[session_id]["user_info"]
        if name:
            context["name"] = name
        if email:
            context["email"] = email
        if phone:
            context["phone"] = phone
        if business:
            context["business"] = business
        if needs:
            for need in needs:
                if need not in context["needs"]:
                    context["needs"].append(need)
        
        context["meeting_interest"] = True
        context["stage"] = "ready_for_meeting"
        if meeting_type:
            context["meeting_preference"] = meeting_type
        if preferred_date:
            context["preferred_day"] = preferred_date
        if preferred_time:
            context["preferred_time"] = preferred_time
        
        # Crear mensaje de confirmación
        if context["name"]:
            confirmation_message = f"¡Gracias {context['name']}! He registrado tu solicitud de reunión. Nuestro equipo te contactará pronto"
        else:
            confirmation_message = "¡Gracias! He registrado tu solicitud de reunión. Nuestro equipo te contactará pronto"
            
        if context["email"] or context["phone"]:
            confirmation_message += " a través de los datos que proporcionaste. ¿Hay algo más en lo que pueda ayudarte?"
        else:
            confirmation_message += ". ¿Podrías proporcionarme tu email o número de teléfono para que puedan contactarte?"
        
        # Guardar respuesta en el historial
        conversation_contexts[session_id]["messages"].append({"role": "assistant", "content": confirmation_message})
        
        result = {
            'session_id': session_id,
            'message': confirmation_message,
            'context': conversation_contexts[session_id]["user_info"],
            'meeting_requested': True
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Get or update configuration"""
    global LOCAL_OLLAMA_URL, MODEL_NAME, EVA_CONTEXT
    
    if request.method == 'GET':
        return jsonify({
            'ollama_url': LOCAL_OLLAMA_URL,
            'model_name': MODEL_NAME,
            'prompt_context': EVA_CONTEXT
        })
    elif request.method == 'POST':
        try:
            data = request.json
            
            if 'ollama_url' in data:
                LOCAL_OLLAMA_URL = data['ollama_url']
            if 'model_name' in data:
                MODEL_NAME = data['model_name']
            if 'prompt_context' in data:
                EVA_CONTEXT = data['prompt_context']
                
            return jsonify({
                'ollama_url': LOCAL_OLLAMA_URL,
                'model_name': MODEL_NAME,
                'prompt_context': EVA_CONTEXT,
                'status': 'updated'
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/available_slots', methods=['GET'])
def available_slots():
    """Endpoint que devuelve slots disponibles para reuniones (simulados)"""
    try:
        # Obtener la fecha actual
        today = datetime.now()
        
        # Generar slots disponibles para los próximos 5 días laborables
        available_slots = []
        
        for i in range(1, 8):  # Próximos 7 días
            current_date = today + timedelta(days=i)
            
            # Saltear fines de semana
            if current_date.weekday() >= 5:  # 5=Sábado, 6=Domingo
                continue
                
            # Generar slots de 1 hora entre 9am y 5pm
            for hour in range(9, 17):
                # Simular que algunos slots ya están ocupados
                if (current_date.day + hour) % 3 != 0:  # Un patrón simple para que algunos slots estén ocupados
                    slot = {
                        'date': current_date.strftime('%Y-%m-%d'),
                        'day': ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][current_date.weekday()],
                        'time': f"{hour}:00",
                        'end_time': f"{hour+1}:00",
                        'available': True
                    }
                    available_slots.append(slot)
        
        return jsonify({
            'slots': available_slots
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/leads', methods=['GET'])
def get_leads():
    """Endpoint para obtener los leads generados (para integración con CRM)"""
    try:
        # Extraer leads basados en conversaciones que han llegado a la etapa ready_for_meeting
        leads = []
        
        for session_id, context in conversation_contexts.items():
            user_info = context["user_info"]
            
            # Solo considerar como leads aquellos que han mostrado interés en una reunión
            if user_info["stage"] == "ready_for_meeting" or user_info["meeting_interest"]:
                # Crear un objeto lead con la información disponible
                lead = {
                    'session_id': session_id,
                    'name': user_info["name"] or "Desconocido",
                    'email': user_info["email"] or None,
                    'phone': user_info["phone"] or None,
                    'business': user_info["business"] or None,
                    'industry': user_info["industry"] or None,
                    'needs': user_info["needs"],
                    'meeting_preference': user_info["meeting_preference"] or "No especificado",
                    'preferred_day': user_info["preferred_day"] or None,
                    'preferred_time': user_info["preferred_time"] or None,
                    'last_interaction': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'complete_info': bool(user_info["email"] or user_info["phone"])
                }
                
                leads.append(lead)
        
        return jsonify({
            'leads': leads,
            'total': len(leads)
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'api_version': '1.1.0',
        'service': 'Eva - Asistente Virtual de Antares Innovate'
    })

# Ruta básica para la raíz
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'name': 'Eva - Asistente Virtual de Antares Innovate',
        'version': '1.1.0',
        'status': 'running',
        'description': 'API para el chatbot Eva de Antares Innovate'
    })

@app.route('/admin', methods=['GET'])
def admin_panel():
    """Panel de administración simplificado"""
    html = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Eva - Panel de Administración</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f8f9fa;
                padding: 20px; 
            }
            .card {
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                margin-bottom: 20px;
            }
            .card-header {
                background-color: #4a4be9;
                color: white;
                border-radius: 10px 10px 0 0 !important;
                font-weight: 600;
            }
            .badge-needs {
                background-color: #6c5ce7;
                color: white;
                margin-right: 4px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="row">
                <div class="col-12 text-center mb-4">
                    <h1>Eva - Asistente Virtual</h1>
                    <p class="lead">Panel de Administración Antares Innovate</p>
                </div>
            </div>
            
            <div class="row">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header">
                            Leads Generados
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-striped" id="leads-table">
                                    <thead>
                                        <tr>
                                            <th>Nombre</th>
                                            <th>Email</th>
                                            <th>Teléfono</th>
                                            <th>Empresa</th>
                                            <th>Necesidades</th>
                                            <th>Última Interacción</th>
                                        </tr>
                                    </thead>
                                    <tbody id="leads-body">
                                        <tr>
                                            <td colspan="6" class="text-center">Cargando leads...</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            Configuración
                        </div>
                        <div class="card-body">
                            <form id="config-form">
                                <div class="mb-3">
                                    <label for="model" class="form-label">Modelo LLM</label>
                                    <input type="text" class="form-control" id="model" name="model">
                                </div>
                                <div class="mb-3">
                                    <label for="url" class="form-label">URL de API</label>
                                    <input type="text" class="form-control" id="url" name="url">
                                </div>
                                <button type="submit" class="btn btn-primary">Guardar</button>
                            </form>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            Estadísticas
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-6">
                                    <div class="card bg-light mb-3">
                                        <div class="card-body text-center">
                                            <h3 id="total-conversations">-</h3>
                                            <p class="mb-0">Conversaciones</p>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="card bg-light mb-3">
                                        <div class="card-body text-center">
                                            <h3 id="total-leads">-</h3>
                                            <p class="mb-0">Leads</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            // Cargar datos al iniciar
            document.addEventListener('DOMContentLoaded', function() {
                loadLeads();
                loadConfig();
                
                // Configurar el formulario
                document.getElementById('config-form').addEventListener('submit', function(e) {
                    e.preventDefault();
                    saveConfig();
                });
            });
            
            // Cargar leads
            function loadLeads() {
                fetch('/api/leads')
                    .then(response => response.json())
                    .then(data => {
                        const leadsTable = document.getElementById('leads-body');
                        document.getElementById('total-leads').textContent = data.total;
                        document.getElementById('total-conversations').textContent = Object.keys(data.leads).length;
                        
                        if (data.leads.length === 0) {
                            leadsTable.innerHTML = '<tr><td colspan="6" class="text-center">No hay leads generados aún</td></tr>';
                            return;
                        }
                        
                        leadsTable.innerHTML = '';
                        data.leads.forEach(lead => {
                            const needsBadges = lead.needs.map(need => 
                                `<span class="badge badge-needs">${need}</span>`
                            ).join(' ');
                            
                            leadsTable.innerHTML += `
                                <tr>
                                    <td>${lead.name}</td>
                                    <td>${lead.email || '-'}</td>
                                    <td>${lead.phone || '-'}</td>
                                    <td>${lead.business || '-'}</td>
                                    <td>${needsBadges || '-'}</td>
                                    <td>${lead.last_interaction}</td>
                                </tr>
                            `;
                        });
                    })
                    .catch(error => console.error('Error:', error));
            }
            
            // Cargar configuración
            function loadConfig() {
                fetch('/api/config')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('model').value = data.model_name;
                        document.getElementById('url').value = data.ollama_url;
                    })
                    .catch(error => console.error('Error:', error));
            }
            
            // Guardar configuración
            function saveConfig() {
                const model = document.getElementById('model').value;
                const url = document.getElementById('url').value;
                
                fetch('/api/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model_name: model,
                        ollama_url: url
                    })
                })
                .then(response => response.json())
                .then(data => {
                    alert('Configuración guardada correctamente');
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error al guardar la configuración');
                });
            }
        </script>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    # Obtener puerto de las variables de entorno o usar 5000 por defecto
    port = int(os.environ.get("PORT", 5000))
    # Usar host 0.0.0.0 para que la aplicación sea accesible desde fuera del contenedor
    app.run(host="0.0.0.0", port=port, debug=False)