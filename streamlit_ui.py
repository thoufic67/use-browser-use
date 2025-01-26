import streamlit as st
import os
import glob
import asyncio
import base64
from dotenv import load_dotenv
import logging
from typing import Optional

# Import your existing modules
from browser_use.agent.service import Agent
from src.utils.agent_state import AgentState
from src.utils import utils
from src.agent.custom_agent import CustomAgent
from src.browser.custom_browser import CustomBrowser
from src.agent.custom_prompts import CustomSystemPrompt
from src.controller.custom_controller import CustomController
from src.utils.default_config_settings import (
    default_config,
    load_config_from_file,
    save_config_to_file
)
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import (
    BrowserContextConfig,
    BrowserContextWindowSize,
)
from src.utils.utils import get_latest_files

# Initialize environment and logging
load_dotenv()
logger = logging.getLogger(__name__)

# Global variables
_global_browser = None
_global_browser_context = None
_global_agent_state = AgentState()

def init_session_state():
    """Initialize session state variables"""
    if 'config' not in st.session_state:
        st.session_state.config = default_config()
    if 'agent_running' not in st.session_state:
        st.session_state.agent_running = False

def sidebar():
    """Create the sidebar with configuration options"""
    with st.sidebar:
        st.title("🛠️ Configuration")
        
        # Theme selection (though Streamlit handles theming differently)
        # st.selectbox(
        #     "Theme",
        #     ["Light", "Dark"],
        #     key="theme",
        #     on_change=lambda: st.query_params(theme=st.session_state.theme.lower())
        # )
        
        # Config file operations
        st.header("Configuration Files")
        config_file = st.file_uploader("Load Config File", type=['pkl'])
        if config_file:
            new_config = load_config_from_file(config_file)
            if new_config:
                st.session_state.config.update(new_config)
                st.success("Configuration loaded successfully!")
        
        if st.button("Save Current Config"):
            save_config_to_file(st.session_state.config)
            st.success("Configuration saved successfully!")

def agent_settings():
    """Agent Settings Section"""
    st.header("⚙️ Agent Settings")
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.config['agent_type'] = st.radio(
            "Agent Type",
            ["org", "custom"],
            help="Select the type of agent to use"
        )
        
        st.session_state.config['use_vision'] = st.checkbox(
            "Use Vision",
            value=st.session_state.config['use_vision'],
            help="Enable visual processing capabilities"
        )
    
    with col2:
        st.session_state.config['max_steps'] = st.slider(
            "Max Run Steps",
            1, 200,
            value=st.session_state.config['max_steps'],
            help="Maximum number of steps the agent will take"
        )
        
        st.session_state.config['max_actions_per_step'] = st.slider(
            "Max Actions per Step",
            1, 20,
            value=st.session_state.config['max_actions_per_step'],
            help="Maximum number of actions per step"
        )

def llm_configuration():
    """LLM Configuration Section"""
    st.header("🔧 LLM Configuration")
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.config['llm_provider'] = st.selectbox(
            "LLM Provider",
            [provider for provider, model in utils.model_names.items()],
            help="Select your preferred language model provider"
        )
        
        st.session_state.config['llm_temperature'] = st.slider(
            "Temperature",
            0.0, 2.0,
            value=st.session_state.config['llm_temperature'],
            step=0.1,
            help="Controls randomness in model outputs"
        )
    
    with col2:
        provider = st.session_state.config['llm_provider']
        model_choices = utils.model_names[provider]
        st.session_state.config['llm_model_name'] = st.selectbox(
            "Model Name",
            model_choices,
            help="Select a model from the available options"
        )
    
    # API Configuration
    st.session_state.config['llm_base_url'] = st.text_input(
        "Base URL",
        value=st.session_state.config['llm_base_url'],
        help="API endpoint URL (if required)"
    )
    
    st.session_state.config['llm_api_key'] = st.text_input(
        "API Key",
        value=st.session_state.config['llm_api_key'],
        type="password",
        help="Your API key (leave blank to use .env)"
    )

def browser_settings():
    """Browser Settings Section"""
    st.header("🌐 Browser Settings")
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.config['use_own_browser'] = st.checkbox(
            "Use Own Browser",
            value=st.session_state.config['use_own_browser'],
            help="Use your existing browser instance"
        )
        
        st.session_state.config['headless'] = st.checkbox(
            "Headless Mode",
            value=st.session_state.config['headless'],
            help="Run browser without GUI"
        )
        
        st.session_state.config['enable_recording'] = st.checkbox(
            "Enable Recording",
            value=st.session_state.config['enable_recording'],
            help="Enable saving browser recordings"
        )
    
    with col2:
        st.session_state.config['keep_browser_open'] = st.checkbox(
            "Keep Browser Open",
            value=st.session_state.config['keep_browser_open'],
            help="Keep Browser Open between Tasks"
        )
        
        st.session_state.config['disable_security'] = st.checkbox(
            "Disable Security",
            value=st.session_state.config['disable_security'],
            help="Disable browser security features"
        )
    
    # Window dimensions
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.config['window_w'] = st.number_input(
            "Window Width",
            value=st.session_state.config['window_w'],
            help="Browser window width"
        )
    
    with col2:
        st.session_state.config['window_h'] = st.number_input(
            "Window Height",
            value=st.session_state.config['window_h'],
            help="Browser window height"
        )
    
    # Paths configuration
    if st.session_state.config['enable_recording']:
        st.session_state.config['save_recording_path'] = st.text_input(
            "Recording Path",
            value=st.session_state.config['save_recording_path'],
            help="Path to save browser recordings"
        )
    
    st.session_state.config['save_trace_path'] = st.text_input(
        "Trace Path",
        value=st.session_state.config['save_trace_path'],
        help="Path to save Agent traces"
    )
    
    st.session_state.config['save_agent_history_path'] = st.text_input(
        "Agent History Save Path",
        value=st.session_state.config['save_agent_history_path'],
        help="Specify the directory where agent history should be saved"
    )

def run_agent_section():
    """Run Agent Section"""
    st.header("🤖 Run Agent")
    
    st.session_state.config['task'] = st.text_area(
        "Task Description",
        value=st.session_state.config['task'],
        help="Describe what you want the agent to do"
    )
    
    add_infos = st.text_area(
        "Additional Information",
        help="Optional hints to help the LLM complete the task"
    )
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if not st.session_state.agent_running:
            if st.button("▶️ Run Agent", type="primary"):
                st.session_state.agent_running = True
                asyncio.run(run_browser_agent(st.session_state.config, add_infos))
    
    with col2:
        if st.session_state.agent_running:
            if st.button("⏹️ Stop"):
                asyncio.run(stop_agent())
                st.session_state.agent_running = False

def results_section():
    """Results Section"""
    st.header("📊 Results")
    
    if 'final_result' in st.session_state:
        st.text_area("Final Result", value=st.session_state.get('final_result', ''), height=100)
        st.text_area("Errors", value=st.session_state.get('errors', ''), height=100)
        st.text_area("Model Actions", value=st.session_state.get('model_actions', ''), height=100)
        st.text_area("Model Thoughts", value=st.session_state.get('model_thoughts', ''), height=100)
    
    if 'latest_recording' in st.session_state and st.session_state['latest_recording']:
        st.video(st.session_state['latest_recording'])

def recordings_section():
    """Recordings Section"""
    st.header("🎥 Recordings")
    
    recording_path = st.session_state.config['save_recording_path']
    if os.path.exists(recording_path):
        recordings = glob.glob(os.path.join(recording_path, "*.[mM][pP]4")) + \
                    glob.glob(os.path.join(recording_path, "*.[wW][eE][bB][mM]"))
        
        if recordings:
            for recording in sorted(recordings, key=os.path.getctime, reverse=True):
                st.video(recording)
        else:
            st.info("No recordings found")
    else:
        st.warning("Recording directory does not exist")

def main():
    st.set_page_config(
        page_title="Browser Use WebUI",
        page_icon="🌐",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    init_session_state()
    sidebar()
    
    st.title("🌐 Browser Use WebUI")
    st.markdown("### Control your browser with AI assistance")
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "⚙️ Agent Settings",
        "🔧 LLM Configuration",
        "🌐 Browser Settings",
        "🤖 Run Agent",
        "📊 Results",
        "🎥 Recordings"
    ])
    
    with tab1:
        agent_settings()
    
    with tab2:
        llm_configuration()
    
    with tab3:
        browser_settings()
    
    with tab4:
        run_agent_section()
    
    with tab5:
        results_section()
    
    with tab6:
        recordings_section()

async def stop_agent():
    """Request the agent to stop and update UI with enhanced feedback"""
    global _global_agent_state, _global_browser_context, _global_browser

    try:
        # Request stop
        _global_agent_state.request_stop()

        # Update UI immediately
        message = "Stop requested - the agent will halt at the next safe point"
        logger.info(f"🛑 {message}")

        # Update session state
        st.session_state.errors = message
        st.session_state.agent_running = False

    except Exception as e:
        error_msg = f"Error during stop: {str(e)}"
        logger.error(error_msg)
        st.session_state.errors = error_msg

async def run_browser_agent(config, add_infos):
    """Run the browser agent with the given configuration"""
    global _global_agent_state, _global_browser, _global_browser_context
    
    _global_agent_state.clear_stop()  # Clear any previous stop requests

    try:
        # Disable recording if not enabled
        save_recording_path = config['save_recording_path'] if config['enable_recording'] else None

        # Ensure the recording directory exists if recording is enabled
        if save_recording_path:
            os.makedirs(save_recording_path, exist_ok=True)

        # Get the list of existing videos before the agent runs
        existing_videos = set()
        if save_recording_path:
            existing_videos = set(
                glob.glob(os.path.join(save_recording_path, "*.[mM][pP]4"))
                + glob.glob(os.path.join(save_recording_path, "*.[wW][eE][bB][mM]"))
            )

        # Get LLM model
        llm = utils.get_llm_model(
            provider=config['llm_provider'],
            model_name=config['llm_model_name'],
            temperature=config['llm_temperature'],
            base_url=config['llm_base_url'],
            api_key=config['llm_api_key'],
        )

        # Run the appropriate agent type
        if config['agent_type'] == "org":
            final_result, errors, model_actions, model_thoughts, trace_file, history_file = await run_org_agent(
                llm=llm,
                use_own_browser=config['use_own_browser'],
                keep_browser_open=config['keep_browser_open'],
                headless=config['headless'],
                disable_security=config['disable_security'],
                window_w=config['window_w'],
                window_h=config['window_h'],
                save_recording_path=save_recording_path,
                save_agent_history_path=config['save_agent_history_path'],
                save_trace_path=config['save_trace_path'],
                task=config['task'],
                max_steps=config['max_steps'],
                use_vision=config['use_vision'],
                max_actions_per_step=config['max_actions_per_step'],
                tool_call_in_content=config.get('tool_call_in_content', False)
            )
        else:  # custom agent
            final_result, errors, model_actions, model_thoughts, trace_file, history_file = await run_custom_agent(
                llm=llm,
                use_own_browser=config['use_own_browser'],
                keep_browser_open=config['keep_browser_open'],
                headless=config['headless'],
                disable_security=config['disable_security'],
                window_w=config['window_w'],
                window_h=config['window_h'],
                save_recording_path=save_recording_path,
                save_agent_history_path=config['save_agent_history_path'],
                save_trace_path=config['save_trace_path'],
                task=config['task'],
                add_infos=add_infos,
                max_steps=config['max_steps'],
                use_vision=config['use_vision'],
                max_actions_per_step=config['max_actions_per_step'],
                tool_call_in_content=config.get('tool_call_in_content', False)
            )

        # Get the latest recording if any
        latest_video = None
        if save_recording_path:
            new_videos = set(
                glob.glob(os.path.join(save_recording_path, "*.[mM][pP]4"))
                + glob.glob(os.path.join(save_recording_path, "*.[wW][eE][bB][mM]"))
            )
            if new_videos - existing_videos:
                latest_video = list(new_videos - existing_videos)[0]

        # Update session state with results
        st.session_state.final_result = final_result
        st.session_state.errors = errors
        st.session_state.model_actions = model_actions
        st.session_state.model_thoughts = model_thoughts
        st.session_state.latest_recording = latest_video
        st.session_state.trace_file = trace_file
        st.session_state.history_file = history_file
        st.session_state.agent_running = False

    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        st.session_state.errors = error_msg
        st.session_state.agent_running = False

async def run_org_agent(
        llm,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        task,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_call_in_content
):
    try:
        global _global_browser, _global_browser_context, _global_agent_state
        
        # Clear any previous stop request
        _global_agent_state.clear_stop()

        if use_own_browser:
            chrome_path = os.getenv("CHROME_PATH", None)
            if chrome_path == "":
                chrome_path = None
        else:
            chrome_path = None

        if _global_browser is None:
            _global_browser = Browser(
                config=BrowserConfig(
                    headless=headless,
                    disable_security=disable_security,
                    chrome_instance_path=chrome_path,
                    extra_chromium_args=[f"--window-size={window_w},{window_h}"],
                )
            )

        if _global_browser_context is None:
            _global_browser_context = await _global_browser.new_context(
                config=BrowserContextConfig(
                    trace_path=save_trace_path if save_trace_path else None,
                    save_recording_path=save_recording_path if save_recording_path else None,
                    no_viewport=False,
                    browser_window_size=BrowserContextWindowSize(
                        width=window_w, height=window_h
                    ),
                )
            )

        agent = Agent(
            task=task,
            llm=llm,
            use_vision=use_vision,
            browser=_global_browser,
            browser_context=_global_browser_context,
            max_actions_per_step=max_actions_per_step,
            tool_call_in_content=tool_call_in_content
        )
        history = await agent.run(max_steps=max_steps)

        history_file = os.path.join(save_agent_history_path, f"{agent.agent_id}.json")
        agent.save_history(history_file)

        return (
            history.final_result(),
            history.errors(),
            history.model_actions(),
            history.model_thoughts(),
            get_latest_files(save_trace_path).get('.zip'),
            history_file
        )
    except Exception as e:
        import traceback
        errors = f"{str(e)}\n{traceback.format_exc()}"
        return '', errors, '', '', None, None
    finally:
        if not keep_browser_open:
            if _global_browser_context:
                await _global_browser_context.close()
                _global_browser_context = None
            if _global_browser:
                await _global_browser.close()
                _global_browser = None

async def run_custom_agent(
        llm,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        task,
        add_infos,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_call_in_content
):
    try:
        global _global_browser, _global_browser_context, _global_agent_state

        _global_agent_state.clear_stop()

        if use_own_browser:
            chrome_path = os.getenv("CHROME_PATH", None)
            if chrome_path == "":
                chrome_path = None
        else:
            chrome_path = None

        controller = CustomController()

        if _global_browser is None:
            _global_browser = CustomBrowser(
                config=BrowserConfig(
                    headless=headless,
                    disable_security=disable_security,
                    chrome_instance_path=chrome_path,
                    extra_chromium_args=[f"--window-size={window_w},{window_h}"],
                )
            )

        if _global_browser_context is None:
            _global_browser_context = await _global_browser.new_context(
                config=BrowserContextConfig(
                    trace_path=save_trace_path if save_trace_path else None,
                    save_recording_path=save_recording_path if save_recording_path else None,
                    no_viewport=False,
                    browser_window_size=BrowserContextWindowSize(
                        width=window_w, height=window_h
                    ),
                )
            )

        agent = CustomAgent(
            task=task,
            add_infos=add_infos,
            use_vision=use_vision,
            llm=llm,
            browser=_global_browser,
            browser_context=_global_browser_context,
            controller=controller,
            system_prompt_class=CustomSystemPrompt,
            max_actions_per_step=max_actions_per_step,
            tool_call_in_content=tool_call_in_content,
            agent_state=_global_agent_state
        )
        history = await agent.run(max_steps=max_steps)

        history_file = os.path.join(save_agent_history_path, f"{agent.agent_id}.json")
        agent.save_history(history_file)

        return (
            history.final_result(),
            history.errors(),
            history.model_actions(),
            history.model_thoughts(),
            get_latest_files(save_trace_path).get('.zip'),
            history_file
        )
    except Exception as e:
        import traceback
        errors = f"{str(e)}\n{traceback.format_exc()}"
        return '', errors, '', '', None, None
    finally:
        if not keep_browser_open:
            if _global_browser_context:
                await _global_browser_context.close()
                _global_browser_context = None
            if _global_browser:
                await _global_browser.close()
                _global_browser = None

if __name__ == "__main__":
    main() 