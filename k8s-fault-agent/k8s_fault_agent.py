"""
Kubernetes Fault Detection and Remediation AI Agent for AgentCert with OpenTelemetry
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

# Kubernetes client - v35+ pattern
from kubernetes import client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException

# OpenAI v2+ client
from openai import OpenAI

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FaultType(Enum):
    """Types of Kubernetes faults that can be detected"""
    POD_CRASH = "pod_crash"
    POD_PENDING = "pod_pending"
    RESOURCE_LIMIT = "resource_limit"
    IMAGE_PULL_ERROR = "image_pull_error"
    CONFIG_ERROR = "config_error"
    NETWORK_ISSUE = "network_issue"
    STORAGE_ISSUE = "storage_issue"
    NODE_NOT_READY = "node_not_ready"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UNKNOWN = "unknown"


class RemediationAction(Enum):
    """Available remediation actions"""
    RESTART_POD = "restart_pod"
    SCALE_DEPLOYMENT = "scale_deployment"
    UPDATE_CONFIG = "update_config"
    INCREASE_RESOURCES = "increase_resources"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    CLEAR_EVICTED_PODS = "clear_evicted_pods"
    PATCH_SERVICE = "patch_service"
    NO_ACTION = "no_action"


@dataclass
class FaultDetectionResult:
    """Structured result for fault detection"""
    timestamp: str
    fault_detected: bool
    fault_type: str
    affected_resource: str
    namespace: str
    severity: str
    description: str
    raw_data: Dict[str, Any]
    
    def to_dict(self):
        return asdict(self)


@dataclass
class RemediationResult:
    """Structured result for remediation action"""
    timestamp: str
    action_taken: str
    success: bool
    affected_resource: str
    namespace: str
    details: str
    error_message: Optional[str] = None
    
    def to_dict(self):
        return asdict(self)


class K8sAgentConfig:
    """Configuration for the Kubernetes Agent"""
    
    def __init__(self):
        # OpenAI Configuration - v2.16.0+
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.openai_baseurl = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        
        # Agent Configuration
        self.namespace = os.getenv("K8S_NAMESPACE", "default")
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "30"))
        self.auto_remediate = os.getenv("AUTO_REMEDIATE", "true").lower() == "true"
        
        # OpenTelemetry Configuration
        self.otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        
        # Validate required configurations
        self._validate()
    
    def _validate(self):
        """Validate required configuration"""
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        if not self.otel_endpoint:
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT is required")


class K8sFaultDetectionAgent:
    """
    AI Agent for Kubernetes Fault Detection and Remediation
    
    This agent:
    1. Monitors Kubernetes resources for faults
    2. Uses LLM to analyze and diagnose issues
    3. Performs remediation actions
    4. Traces all operations to Open Telemetry collector
    """
    
    def __init__(self, config: K8sAgentConfig):
        self.config = config
        
        # Initialize Kubernetes client - v35+ pattern
        # Use proper kubernetes.config module (not config.load_*)
        try:
            # Try in-cluster configuration first (for pods)
            k8s_config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except k8s_config.ConfigException:
            # Fall back to kubeconfig file (for local development)
            try:
                k8s_config.load_kube_config()
                logger.info("Loaded kubeconfig Kubernetes configuration")
            except k8s_config.ConfigException as e:
                logger.error(f"Failed to load Kubernetes configuration: {e}")
                raise
        
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        
        # Initialize OpenAI client - v2.16.0+ pattern
        self.openai_client = OpenAI(api_key=self.config.openai_api_key, base_url=self.config.openai_baseurl)
        
        # Initialize OpenTelemetry
        self._setup_otel()
        
        logger.info("K8s Fault Detection Agent initialized successfully")
        logger.info(f"Using OpenAI model: {self.config.openai_model}")
    
    def _setup_otel(self):
        """
        Setup OpenTelemetry tracing with OTLP exporter
        
        This sends traces to the OTEL collector endpoint specified in
        OTEL_EXPORTER_OTLP_ENDPOINT environment variable.
        """
        resource = Resource.create({
            "service.name": "k8s-fault-agent",
            "service.version": "1.2.0",
            "deployment.environment": os.getenv("DEPLOYMENT_ENV", "production")
        })
        
        provider = TracerProvider(resource=resource)
        
        # Configure OTLP exporter
        # This sends traces to an OTEL collector
        otlp_exporter = OTLPSpanExporter(
            endpoint=self.config.otel_endpoint,
            insecure=True  # Use insecure for localhost, configure TLS for production
        )
        
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)
        
        self.tracer = trace.get_tracer(__name__)
        logger.info(f"OpenTelemetry configured with endpoint: {self.config.otel_endpoint}")
    
    def get_pod_status(self, namespace: str = None) -> List[Dict]:
        """
        Get status of all pods in namespace
        
        Args:
            namespace: Kubernetes namespace (defaults to configured namespace)
            
        Returns:
            List of pod status dictionaries
        """
        namespace = namespace or self.config.namespace
        
        with self.tracer.start_as_current_span("get_pod_status") as span:
            span.set_attribute("namespace", namespace)
            
            try:
                pods = self.v1.list_namespaced_pod(namespace)
                pod_statuses = []
                
                for pod in pods.items:
                    pod_info = {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "phase": pod.status.phase,
                        "conditions": [],
                        "container_statuses": []
                    }
                    
                    # Get pod conditions
                    if pod.status.conditions:
                        pod_info["conditions"] = [
                            {
                                "type": cond.type,
                                "status": cond.status,
                                "reason": cond.reason,
                                "message": cond.message
                            }
                            for cond in pod.status.conditions
                        ]
                    
                    # Get container statuses
                    if pod.status.container_statuses:
                        pod_info["container_statuses"] = [
                            {
                                "name": cs.name,
                                "ready": cs.ready,
                                "restart_count": cs.restart_count,
                                "state": self._get_container_state(cs.state)
                            }
                            for cs in pod.status.container_statuses
                        ]
                    
                    pod_statuses.append(pod_info)
                
                span.set_attribute("pods_count", len(pod_statuses))
                
                return pod_statuses
                
            except ApiException as e:
                logger.error(f"Error getting pod status: {e}")
                span.set_attribute("error", str(e))
                raise
    
    def _get_container_state(self, state) -> Dict:
        """Extract container state information"""
        if state.running:
            return {"status": "running", "started_at": str(state.running.started_at)}
        elif state.waiting:
            return {
                "status": "waiting",
                "reason": state.waiting.reason,
                "message": state.waiting.message
            }
        elif state.terminated:
            return {
                "status": "terminated",
                "reason": state.terminated.reason,
                "exit_code": state.terminated.exit_code,
                "message": state.terminated.message
            }
        return {"status": "unknown"}
    
    def detect_faults(self, namespace: str = None) -> List[FaultDetectionResult]:
        """
        Detect faults in Kubernetes resources
        
        Args:
            namespace: Kubernetes namespace
            
        Returns:
            List of detected faults
        """
        namespace = namespace or self.config.namespace
        detected_faults = []
        
        with self.tracer.start_as_current_span("detect_faults") as span:
            span.set_attribute("namespace", namespace)
            
            # Get pod statuses
            pod_statuses = self.get_pod_status(namespace)
            
            for pod in pod_statuses:
                fault = self._analyze_pod_for_faults(pod)
                if fault:
                    detected_faults.append(fault)
            
            span.set_attribute("faults_detected", len(detected_faults))
            
            logger.info(f"Detected {len(detected_faults)} faults in namespace {namespace}")
            
            return detected_faults
    
    def _analyze_pod_for_faults(self, pod: Dict) -> Optional[FaultDetectionResult]:
        """
        Analyze a single pod for faults
        
        Args:
            pod: Pod information dictionary
            
        Returns:
            FaultDetectionResult if fault detected, None otherwise
        """
        timestamp = datetime.utcnow().isoformat()
        
        # Check if pod is not running
        if pod["phase"] != "Running":
            fault_type = FaultType.UNKNOWN
            description = f"Pod {pod['name']} is in {pod['phase']} state"
            
            # Determine specific fault type
            if pod["phase"] == "Pending":
                fault_type = FaultType.POD_PENDING
            elif pod["phase"] == "Failed":
                fault_type = FaultType.POD_CRASH
            
            # Check container statuses for more details
            for cs in pod.get("container_statuses", []):
                state = cs.get("state", {})
                if state.get("status") == "waiting":
                    reason = state.get("reason", "")
                    if "ImagePull" in reason or "ErrImage" in reason:
                        fault_type = FaultType.IMAGE_PULL_ERROR
                        description = f"Image pull error: {state.get('message', '')}"
                    elif "CrashLoopBackOff" in reason:
                        fault_type = FaultType.POD_CRASH
                        description = f"Container crash loop: {state.get('message', '')}"
            
            return FaultDetectionResult(
                timestamp=timestamp,
                fault_detected=True,
                fault_type=fault_type.value,
                affected_resource=f"pod/{pod['name']}",
                namespace=pod["namespace"],
                severity="high",
                description=description,
                raw_data=pod
            )
        
        # Check for high restart count
        for cs in pod.get("container_statuses", []):
            if cs.get("restart_count", 0) > 5:
                return FaultDetectionResult(
                    timestamp=timestamp,
                    fault_detected=True,
                    fault_type=FaultType.POD_CRASH.value,
                    affected_resource=f"pod/{pod['name']}",
                    namespace=pod["namespace"],
                    severity="medium",
                    description=f"High restart count: {cs['restart_count']}",
                    raw_data=pod
                )
        
        return None
    
    def analyze_fault_with_llm(self, fault: FaultDetectionResult) -> Dict[str, Any]:
        """
        Use LLM to analyze the fault and suggest remediation
        
        Args:
            fault: Detected fault
            
        Returns:
            Analysis and remediation suggestion
        """
        with self.tracer.start_as_current_span("analyze_fault_with_llm") as span:
            span.set_attribute("fault_type", fault.fault_type)
            span.set_attribute("resource", fault.affected_resource)
            
            # Construct prompt for LLM
            prompt = self._construct_analysis_prompt(fault)
            
            try:
                # Use OpenAI v2+ client pattern
                response = self.openai_client.chat.completions.create(
                    model=self.config.openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert Kubernetes operations engineer. Analyze the fault and provide remediation steps in JSON format."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3,
                    max_tokens=500
                )
                
                analysis_text = response.choices[0].message.content
                
                # Try to parse as JSON
                try:
                    analysis = json.loads(analysis_text)
                except json.JSONDecodeError:
                    # If not valid JSON, create structured response
                    analysis = {
                        "root_cause": "Analysis pending",
                        "recommended_action": RemediationAction.NO_ACTION.value,
                        "explanation": analysis_text
                    }
                
                span.set_attribute("recommended_action", analysis.get("recommended_action", "unknown"))
                
                return analysis
                
            except Exception as e:
                logger.error(f"Error analyzing fault with LLM: {e}")
                span.set_attribute("error", str(e))
                return {
                    "root_cause": "LLM analysis failed",
                    "recommended_action": RemediationAction.NO_ACTION.value,
                    "explanation": str(e)
                }
    
    def _construct_analysis_prompt(self, fault: FaultDetectionResult) -> str:
        """Construct prompt for LLM analysis"""
        return f"""
        Analyze the following Kubernetes fault and provide remediation steps.
        
        Fault Type: {fault.fault_type}
        Affected Resource: {fault.affected_resource}
        Namespace: {fault.namespace}
        Severity: {fault.severity}
        Description: {fault.description}
        
        Raw Data:
        {json.dumps(fault.raw_data, indent=2)}
        
        Provide your analysis in the following JSON format:
        {{
            "root_cause": "Brief explanation of the root cause",
            "recommended_action": "One of: restart_pod, scale_deployment, update_config, increase_resources, rollback_deployment, no_action",
            "explanation": "Detailed explanation and steps to remediate",
            "risk_level": "low/medium/high"
        }}
        """
    
    def remediate_fault(
        self,
        fault: FaultDetectionResult,
        action: RemediationAction,
        dry_run: bool = False
    ) -> RemediationResult:
        """
        Perform remediation action for a fault
        
        Args:
            fault: Detected fault
            action: Remediation action to perform
            dry_run: If True, only simulate the action
            
        Returns:
            RemediationResult
        """
        timestamp = datetime.utcnow().isoformat()
        
        with self.tracer.start_as_current_span("remediate_fault") as span:
            span.set_attribute("fault_type", fault.fault_type)
            span.set_attribute("action", action.value)
            span.set_attribute("dry_run", dry_run)
            
            try:
                if action == RemediationAction.RESTART_POD:
                    result = self._restart_pod(fault, dry_run)
                elif action == RemediationAction.SCALE_DEPLOYMENT:
                    result = self._scale_deployment(fault, dry_run)
                elif action == RemediationAction.CLEAR_EVICTED_PODS:
                    result = self._clear_evicted_pods(fault, dry_run)
                else:
                    result = RemediationResult(
                        timestamp=timestamp,
                        action_taken=action.value,
                        success=False,
                        affected_resource=fault.affected_resource,
                        namespace=fault.namespace,
                        details="Action not implemented",
                        error_message="This remediation action is not yet implemented"
                    )
                
                span.set_attribute("success", result.success)
                
                return result
                
            except Exception as e:
                logger.error(f"Error during remediation: {e}")
                span.set_attribute("error", str(e))
                
                return RemediationResult(
                    timestamp=timestamp,
                    action_taken=action.value,
                    success=False,
                    affected_resource=fault.affected_resource,
                    namespace=fault.namespace,
                    details="Remediation failed",
                    error_message=str(e)
                )
    
    def _restart_pod(self, fault: FaultDetectionResult, dry_run: bool) -> RemediationResult:
        """Restart a pod by deleting it"""
        timestamp = datetime.utcnow().isoformat()
        pod_name = fault.affected_resource.split("/")[-1]
        
        if dry_run:
            return RemediationResult(
                timestamp=timestamp,
                action_taken=RemediationAction.RESTART_POD.value,
                success=True,
                affected_resource=fault.affected_resource,
                namespace=fault.namespace,
                details=f"[DRY RUN] Would delete pod {pod_name}"
            )
        
        try:
            self.v1.delete_namespaced_pod(
                name=pod_name,
                namespace=fault.namespace,
                body=client.V1DeleteOptions()
            )
            
            return RemediationResult(
                timestamp=timestamp,
                action_taken=RemediationAction.RESTART_POD.value,
                success=True,
                affected_resource=fault.affected_resource,
                namespace=fault.namespace,
                details=f"Successfully deleted pod {pod_name}. It will be recreated by its controller."
            )
        except ApiException as e:
            return RemediationResult(
                timestamp=timestamp,
                action_taken=RemediationAction.RESTART_POD.value,
                success=False,
                affected_resource=fault.affected_resource,
                namespace=fault.namespace,
                details=f"Failed to delete pod {pod_name}",
                error_message=str(e)
            )
    
    def _scale_deployment(self, fault: FaultDetectionResult, dry_run: bool) -> RemediationResult:
        """Scale a deployment"""
        timestamp = datetime.utcnow().isoformat()
        
        # This is a placeholder - in real implementation, you'd need to identify the deployment
        return RemediationResult(
            timestamp=timestamp,
            action_taken=RemediationAction.SCALE_DEPLOYMENT.value,
            success=False,
            affected_resource=fault.affected_resource,
            namespace=fault.namespace,
            details="Scale deployment action requires deployment name",
            error_message="Not implemented for pod-level faults"
        )
    
    def _clear_evicted_pods(self, fault: FaultDetectionResult, dry_run: bool) -> RemediationResult:
        """Clear evicted pods from namespace"""
        timestamp = datetime.utcnow().isoformat()
        
        try:
            pods = self.v1.list_namespaced_pod(fault.namespace)
            evicted_pods = [
                pod for pod in pods.items
                if pod.status.phase == "Failed" and pod.status.reason == "Evicted"
            ]
            
            if dry_run:
                return RemediationResult(
                    timestamp=timestamp,
                    action_taken=RemediationAction.CLEAR_EVICTED_PODS.value,
                    success=True,
                    affected_resource=fault.affected_resource,
                    namespace=fault.namespace,
                    details=f"[DRY RUN] Would delete {len(evicted_pods)} evicted pods"
                )
            
            deleted_count = 0
            for pod in evicted_pods:
                try:
                    self.v1.delete_namespaced_pod(
                        name=pod.metadata.name,
                        namespace=fault.namespace,
                        body=client.V1DeleteOptions()
                    )
                    deleted_count += 1
                except ApiException:
                    pass
            
            return RemediationResult(
                timestamp=timestamp,
                action_taken=RemediationAction.CLEAR_EVICTED_PODS.value,
                success=True,
                affected_resource=fault.affected_resource,
                namespace=fault.namespace,
                details=f"Deleted {deleted_count} evicted pods"
            )
        except Exception as e:
            return RemediationResult(
                timestamp=timestamp,
                action_taken=RemediationAction.CLEAR_EVICTED_PODS.value,
                success=False,
                affected_resource=fault.affected_resource,
                namespace=fault.namespace,
                details="Failed to clear evicted pods",
                error_message=str(e)
            )
    
    def run_agent_cycle(self, namespace: str = None) -> Dict[str, Any]:
        """
        Run a complete agent cycle: detect, analyze, and remediate
        
        Args:
            namespace: Kubernetes namespace
            
        Returns:
            Summary of the cycle
        """
        namespace = namespace or self.config.namespace
        
        with self.tracer.start_as_current_span("run_agent_cycle") as span:
            span.set_attribute("namespace", namespace)
            
            cycle_summary = {
                "timestamp": datetime.utcnow().isoformat(),
                "namespace": namespace,
                "faults_detected": 0,
                "faults_analyzed": 0,
                "remediations_attempted": 0,
                "remediations_successful": 0,
                "details": []
            }
            
            # Detect faults
            faults = self.detect_faults(namespace)
            cycle_summary["faults_detected"] = len(faults)
            
            # Process each fault
            for fault in faults:
                fault_detail = {
                    "fault": fault.to_dict(),
                    "analysis": None,
                    "remediation": None
                }
                
                # Analyze with LLM
                analysis = self.analyze_fault_with_llm(fault)
                fault_detail["analysis"] = analysis
                cycle_summary["faults_analyzed"] += 1
                
                # Remediate if auto-remediation is enabled
                if self.config.auto_remediate:
                    recommended_action = analysis.get("recommended_action", "no_action")
                    
                    if recommended_action != "no_action":
                        try:
                            action = RemediationAction(recommended_action)
                            remediation = self.remediate_fault(fault, action, dry_run=False)
                            fault_detail["remediation"] = remediation.to_dict()
                            cycle_summary["remediations_attempted"] += 1
                            
                            if remediation.success:
                                cycle_summary["remediations_successful"] += 1
                        except ValueError:
                            logger.warning(f"Unknown remediation action: {recommended_action}")
                
                cycle_summary["details"].append(fault_detail)
            
            span.set_attribute("faults_detected", cycle_summary["faults_detected"])
            span.set_attribute("remediations_successful", cycle_summary["remediations_successful"])
            
            return cycle_summary


def main():
    """Main entry point for the agent"""
    logger.info("Starting K8s Fault Detection Agent")
    
    try:
        # Load configuration
        config = K8sAgentConfig()
        
        # Create agent
        agent = K8sFaultDetectionAgent(config)
        
        # Run one cycle (for testing)
        logger.info("Running agent cycle...")
        result = agent.run_agent_cycle()
        
        # Print results
        logger.info("Agent cycle completed:")
        logger.info(json.dumps(result, indent=2))
        
    except Exception as e:
        logger.error(f"Error running agent: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
