"""
Kubernetes Fault Detection and Remediation AI Agent
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass, asdict

# Kubernetes client
from kubernetes import client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException

# OpenAI SDK - ONLY for communicating with LiteLLM gateway
from openai import OpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class FaultContext:
    """Context information about a detected fault"""
    timestamp: str
    namespace: str
    resource_type: str
    resource_name: str
    status: str
    conditions: List[Dict]
    container_statuses: List[Dict]
    events: List[str]
    
    def to_dict(self):
        return asdict(self)
    
    def to_prompt(self) -> str:
        """Convert fault context to LLM prompt"""
        return f"""
Kubernetes Fault Detected:

Resource: {self.resource_type}/{self.resource_name}
Namespace: {self.namespace}
Current Status: {self.status}
Timestamp: {self.timestamp}

Conditions:
{json.dumps(self.conditions, indent=2)}

Container Statuses:
{json.dumps(self.container_statuses, indent=2)}

Recent Events:
{chr(10).join(self.events)}

Please analyze this fault and provide:
1. Root cause analysis
2. Recommended remediation action
3. Step-by-step remediation instructions
4. Risk assessment

Respond in JSON format with keys: root_cause, action, steps, risk_level
"""


@dataclass
class AgentDecision:
    """Decision made by the autonomous agent"""
    timestamp: str
    fault_context: FaultContext
    llm_reasoning: str
    root_cause: str
    recommended_action: str
    remediation_steps: List[str]
    risk_level: str
    confidence: float
    
    def to_dict(self):
        result = asdict(self)
        result['fault_context'] = self.fault_context.to_dict()
        return result


class AutonomousAgentConfig:
    """
    Configuration for the Autonomous Agent
    """
    
    def __init__(self):
        # LLM Gateway Configuration (LiteLLM)
        self.gateway_url = os.getenv("LITELLM_URL")
        self.gateway_api_key = os.getenv("LITELLM_MASTER_KEY")
        
        # Model alias - LiteLLM maps this to actual model
        self.model_alias = os.getenv("MODEL_ALIAS")
        
        # Agent Configuration
        self.namespace = os.getenv("K8S_NAMESPACE")
        self.auto_remediate = os.getenv("AUTO_REMEDIATE", "false").lower() == "true"
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        
        # Agent Identity (for tracing metadata)
        self.agent_id = os.getenv("AGENT_ID", f"agent-{os.getenv('HOSTNAME', 'local')}")
        self.session_id = os.getenv("SESSION_ID", f"session-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        
        # Validate
        self._validate()
    
    def _validate(self):
        """Validate configuration"""
        if not self.gateway_url:
            raise ValueError("LITELLM_URL environment variable is required")
        if not self.gateway_api_key:
            raise ValueError("LITELLM_MASTER_KEY environment variable is required")
        if not self.model_alias:
            raise ValueError("MODEL_ALIAS environment variable is required")
        if not self.namespace:
            raise ValueError("K8S_NAMESPACE environment variable is required")
        
        logger.info(f"Agent configured with LLM Gateway: {self.gateway_url}")
        logger.info(f"Agent model alias: {self.model_alias}")
        logger.info(f"Monitoring namespace: {self.namespace}")


class AutonomousK8sFaultAgent:
    """
    Fully Autonomous Kubernetes Fault Detection and Remediation Agent
    """
    
    def __init__(self, config: AutonomousAgentConfig):
        self.config = config
        
        # Initialize Kubernetes client
        try:
            k8s_config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except k8s_config.ConfigException:
            try:
                k8s_config.load_kube_config()
                logger.info("Loaded local Kubernetes configuration")
            except k8s_config.ConfigException as e:
                logger.error(f"Failed to load Kubernetes configuration: {e}")
                raise
        
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        
        # Initialize LLM client
        self.llm_gateway = OpenAI(
            api_key=self.config.gateway_api_key,
            base_url=f"{self.config.gateway_url}/v1"
        )
        
        logger.info("=" * 60)
        logger.info("Autonomous K8s Fault Detection Agent Initialized")
        logger.info(f"LLM Gateway: {self.config.gateway_url}")
        logger.info(f"Model Alias: {self.config.model_alias}")
        logger.info(f"Agent ID: {self.config.agent_id}")
        logger.info(f"Session: {self.config.session_id}")
        logger.info("=" * 60)
    
    def gather_fault_context(self, namespace: str = None) -> List[FaultContext]:
        """
        Gather context about current cluster state
        Returns list of fault contexts for unhealthy resources
        """
        namespace = namespace or self.config.namespace
        faults = []
        
        try:
            # Get all pods
            pods = self.v1.list_namespaced_pod(namespace)
            
            for pod in pods.items:
                # Check if pod is in unhealthy state
                if pod.status.phase not in ["Running", "Succeeded"]:
                    fault_context = self._extract_pod_fault_context(pod)
                    faults.append(fault_context)
                
                # Also check for high restart counts even if running
                elif pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        if cs.restart_count > 5:
                            fault_context = self._extract_pod_fault_context(pod)
                            faults.append(fault_context)
                            break
            
            logger.info(f"Gathered {len(faults)} fault contexts from namespace {namespace}")
            return faults
            
        except ApiException as e:
            logger.error(f"Error gathering fault context: {e}")
            return []
    
    def _extract_pod_fault_context(self, pod) -> FaultContext:
        """Extract fault context from a pod"""
        # Get pod conditions
        conditions = []
        if pod.status.conditions:
            conditions = [
                {
                    "type": cond.type,
                    "status": cond.status,
                    "reason": cond.reason if cond.reason else "Unknown",
                    "message": cond.message if cond.message else ""
                }
                for cond in pod.status.conditions
            ]
        
        # Get container statuses
        container_statuses = []
        if pod.status.container_statuses:
            container_statuses = [
                {
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": self._get_container_state(cs.state)
                }
                for cs in pod.status.container_statuses
            ]
        
        # Get recent events
        events = []
        try:
            field_selector = f"involvedObject.name={pod.metadata.name}"
            event_list = self.v1.list_namespaced_event(
                pod.metadata.namespace,
                field_selector=field_selector
            )
            events = [
                f"{event.last_timestamp}: {event.reason} - {event.message}"
                for event in event_list.items[:5]  # Last 5 events
            ]
        except:
            pass
        
        return FaultContext(
            timestamp=datetime.utcnow().isoformat(),
            namespace=pod.metadata.namespace,
            resource_type="pod",
            resource_name=pod.metadata.name,
            status=pod.status.phase,
            conditions=conditions,
            container_statuses=container_statuses,
            events=events
        )
    
    def _get_container_state(self, state) -> Dict:
        """Extract container state"""
        if state.running:
            return {"status": "running", "started_at": str(state.running.started_at)}
        elif state.waiting:
            return {
                "status": "waiting",
                "reason": state.waiting.reason if state.waiting.reason else "Unknown",
                "message": state.waiting.message if state.waiting.message else ""
            }
        elif state.terminated:
            return {
                "status": "terminated",
                "reason": state.terminated.reason if state.terminated.reason else "Unknown",
                "exit_code": state.terminated.exit_code,
                "message": state.terminated.message if state.terminated.message else ""
            }
        return {"status": "unknown"}
    
    def ask_llm_for_decision(self, fault_context: FaultContext) -> AgentDecision:
        """
        Ask LLM (via gateway) to analyze fault and decide on remediation
        """
        logger.info(f"Consulting LLM Gateway for: {fault_context.resource_type}/{fault_context.resource_name}")
        
        # Prepare metadata for LiteLLM
        # LiteLLM will enrich this with provider-specific details
        request_metadata = {
            "agent_id": self.config.agent_id,
            "session_id": self.config.session_id,
            "fault_resource": f"{fault_context.resource_type}/{fault_context.resource_name}",
            "fault_namespace": fault_context.namespace,
            "fault_status": fault_context.status,
            "timestamp": fault_context.timestamp,
            "agent_version": "2.1.0"
        }
        
        try:
            # Call LLM gateway
            response = self.llm_gateway.chat.completions.create(
                model=self.config.model_alias,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an autonomous Kubernetes SRE agent. Analyze faults and provide remediation decisions.

IMPORTANT: Always respond in valid JSON format with these exact keys:
{
  "root_cause": "Brief explanation of what caused the issue",
  "action": "One of: restart_pod, delete_pod, scale_deployment, no_action, investigate",
  "steps": ["Step 1", "Step 2", ...],
  "risk_level": "low/medium/high"
}"""
                    },
                    {
                        "role": "user",
                        "content": fault_context.to_prompt()
                    }
                ],
                temperature=0.3,
                max_tokens=1000,
                # Send metadata to LiteLLM for tracing
                extra_body={
                    "metadata": request_metadata
                }
            )
            
            # Parse LLM response
            llm_response = response.choices[0].message.content
            logger.info(f"LLM response received (via gateway)")
            
            # Try to parse as JSON
            try:
                decision_data = json.loads(llm_response)
            except json.JSONDecodeError:
                logger.warning("LLM response not valid JSON, using fallback")
                decision_data = {
                    "root_cause": "Unable to parse LLM response",
                    "action": "investigate",
                    "steps": ["Review LLM response manually"],
                    "risk_level": "medium"
                }
            
            # Create agent decision
            return AgentDecision(
                timestamp=datetime.utcnow().isoformat(),
                fault_context=fault_context,
                llm_reasoning=llm_response,
                root_cause=decision_data.get("root_cause", "Unknown"),
                recommended_action=decision_data.get("action", "investigate"),
                remediation_steps=decision_data.get("steps", []),
                risk_level=decision_data.get("risk_level", "medium"),
                confidence=0.8
            )
            
        except Exception as e:
            logger.error(f"Error consulting LLM gateway: {e}")
            
            # Fallback decision
            return AgentDecision(
                timestamp=datetime.utcnow().isoformat(),
                fault_context=fault_context,
                llm_reasoning=f"Gateway error: {str(e)}",
                root_cause="LLM gateway consultation failed",
                recommended_action="investigate",
                remediation_steps=["Manual investigation required", "Check LLM gateway logs"],
                risk_level="high",
                confidence=0.0
            )
    
    def execute_remediation(self, decision: AgentDecision) -> Dict[str, any]:
        """Execute the remediation action decided by LLM"""
        action = decision.recommended_action
        fault_ctx = decision.fault_context
        
        logger.info(f"Executing remediation: {action} for {fault_ctx.resource_name}")
        
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would execute: {action}")
            return {
                "success": True,
                "dry_run": True,
                "action": action,
                "message": f"Would execute {action} on {fault_ctx.resource_name}"
            }
        
        # Execute actual remediation based on LLM decision
        if action == "restart_pod" or action == "delete_pod":
            return self._restart_pod(fault_ctx)
        elif action == "scale_deployment":
            return self._scale_deployment(fault_ctx)
        elif action == "investigate":
            return {
                "success": True,
                "action": "investigate",
                "message": "Manual investigation recommended"
            }
        elif action == "no_action":
            return {
                "success": True,
                "action": "no_action",
                "message": "No action needed"
            }
        else:
            return {
                "success": False,
                "action": action,
                "message": f"Unknown action: {action}"
            }
    
    def _restart_pod(self, fault_context: FaultContext) -> Dict:
        """Restart pod by deleting it"""
        try:
            self.v1.delete_namespaced_pod(
                name=fault_context.resource_name,
                namespace=fault_context.namespace,
                body=client.V1DeleteOptions()
            )
            
            return {
                "success": True,
                "action": "restart_pod",
                "message": f"Successfully deleted pod {fault_context.resource_name}"
            }
        except ApiException as e:
            return {
                "success": False,
                "action": "restart_pod",
                "error": str(e)
            }
    
    def _scale_deployment(self, fault_context: FaultContext) -> Dict:
        """Scale deployment (placeholder)"""
        return {
            "success": False,
            "action": "scale_deployment",
            "message": "Not implemented - requires deployment identification"
        }
    
    def run_autonomous_cycle(self, namespace: str = None) -> Dict:
        """
        Run complete autonomous agent cycle
        """
        namespace = namespace or self.config.namespace
        
        logger.info(f"Starting autonomous agent cycle for namespace: {namespace}")
        
        cycle_summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": self.config.agent_id,
            "session_id": self.config.session_id,
            "namespace": namespace,
            "faults_detected": 0,
            "decisions_made": 0,
            "actions_executed": 0,
            "actions_successful": 0,
            "details": []
        }
        
        # Step 1: Gather fault contexts
        fault_contexts = self.gather_fault_context(namespace)
        cycle_summary["faults_detected"] = len(fault_contexts)
        
        # Step 2: Process each fault autonomously
        for fault_ctx in fault_contexts:
            fault_detail = {
                "fault": fault_ctx.to_dict(),
                "decision": None,
                "execution": None
            }
            
            # Ask LLM for decision (via gateway)
            decision = self.ask_llm_for_decision(fault_ctx)
            fault_detail["decision"] = decision.to_dict()
            cycle_summary["decisions_made"] += 1
            
            # Execute if auto-remediation enabled
            if self.config.auto_remediate and decision.risk_level in ["low", "medium"]:
                execution_result = self.execute_remediation(decision)
                fault_detail["execution"] = execution_result
                cycle_summary["actions_executed"] += 1
                
                if execution_result.get("success", False):
                    cycle_summary["actions_successful"] += 1
            else:
                logger.info(f"Skipping execution (auto_remediate={self.config.auto_remediate}, risk={decision.risk_level})")
                fault_detail["execution"] = {
                    "skipped": True,
                    "reason": "auto_remediate disabled or risk too high"
                }
            
            cycle_summary["details"].append(fault_detail)
        
        logger.info(f"Cycle completed: {cycle_summary['faults_detected']} faults, {cycle_summary['actions_executed']} actions")
        
        return cycle_summary


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Autonomous K8s Fault Detection Agent")
    logger.info("Properly Abstracted Gateway")
    logger.info("=" * 60)
    
    try:
        # Load configuration
        config = AutonomousAgentConfig()
        
        # Create agent
        agent = AutonomousK8sFaultAgent(config)
        
        # Run autonomous cycle
        logger.info("Running autonomous agent cycle...")
        result = agent.run_autonomous_cycle()
        
        # Print results
        logger.info("=" * 60)
        logger.info("Cycle Summary:")
        logger.info(json.dumps(result, indent=2))
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error running autonomous agent: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
