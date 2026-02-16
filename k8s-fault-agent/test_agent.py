#!/usr/bin/env python3
"""
Standalone test script for K8s Fault Detection Agent
Run this before deploying to Kubernetes to test the agent locally
"""

import os
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from k8s_fault_agent import (
    K8sAgentConfig,
    K8sFaultDetectionAgent,
    FaultDetectionResult,
    FaultType
)


def test_configuration():
    """Test 1: Verify configuration loads correctly"""
    print("=" * 60)
    print("TEST 1: Configuration Validation")
    print("=" * 60)
    
    try:
        config = K8sAgentConfig()
        print("✓ Configuration loaded successfully")
        print(f"  - Namespace: {config.namespace}")
        print(f"  - Check Interval: {config.check_interval}s")
        print(f"  - Auto Remediate: {config.auto_remediate}")
        print(f"  - OpenAI Model: {config.openai_model}")
        print(f"  - OpenAI Base URL: {config.openai_baseurl}")
        return True
    except Exception as e:
        print(f"✗ Configuration failed: {e}")
        return False


def test_k8s_connection():
    """Test 2: Verify Kubernetes connection"""
    print("\n" + "=" * 60)
    print("TEST 2: Kubernetes Connection")
    print("=" * 60)
    
    try:
        config = K8sAgentConfig()
        agent = K8sFaultDetectionAgent(config)
        print("✓ Kubernetes client initialized")
        
        # Try to get pod status
        pods = agent.get_pod_status()
        print(f"✓ Successfully retrieved status of {len(pods)} pods")
        
        # Display first few pods
        for i, pod in enumerate(pods[:3]):
            print(f"\n  Pod {i+1}: {pod['name']}")
            print(f"    Phase: {pod['phase']}")
            print(f"    Namespace: {pod['namespace']}")
        
        if len(pods) > 3:
            print(f"\n  ... and {len(pods) - 3} more pods")
        
        return True
    except Exception as e:
        print(f"✗ Kubernetes connection failed: {e}")
        return False


def test_fault_detection():
    """Test 3: Test fault detection capabilities"""
    print("\n" + "=" * 60)
    print("TEST 3: Fault Detection")
    print("=" * 60)
    
    try:
        config = K8sAgentConfig()
        agent = K8sFaultDetectionAgent(config)
        
        # Detect faults
        faults = agent.detect_faults()
        print(f"✓ Fault detection completed")
        print(f"  - Faults detected: {len(faults)}")
        
        # Display detected faults
        for i, fault in enumerate(faults[:5]):
            print(f"\n  Fault {i+1}:")
            print(f"    Type: {fault.fault_type}")
            print(f"    Resource: {fault.affected_resource}")
            print(f"    Severity: {fault.severity}")
            print(f"    Description: {fault.description}")
        
        if len(faults) > 5:
            print(f"\n  ... and {len(faults) - 5} more faults")
        
        return True
    except Exception as e:
        print(f"✗ Fault detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_llm_analysis():
    """Test 4: Test LLM analysis"""
    print("\n" + "=" * 60)
    print("TEST 4: LLM Analysis")
    print("=" * 60)
    
    try:
        config = K8sAgentConfig()
        agent = K8sFaultDetectionAgent(config)
        
        # Create a sample fault for testing
        sample_fault = FaultDetectionResult(
            timestamp="2024-02-04T10:00:00Z",
            fault_detected=True,
            fault_type=FaultType.POD_PENDING.value,
            affected_resource="pod/test-pod",
            namespace="default",
            severity="high",
            description="Pod is stuck in Pending state",
            raw_data={
                "name": "test-pod",
                "phase": "Pending",
                "conditions": [
                    {
                        "type": "PodScheduled",
                        "status": "False",
                        "reason": "Unschedulable",
                        "message": "0/3 nodes are available: insufficient memory"
                    }
                ]
            }
        )
        
        print("  Analyzing sample fault...")
        analysis = agent.analyze_fault_with_llm(sample_fault)
        
        print("✓ LLM analysis completed")
        print(f"\n  Analysis Results:")
        print(json.dumps(analysis, indent=4))
        
        return True
    except Exception as e:
        print(f"✗ LLM analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_otel_tracing():
    """Test 5: Verify OTEL tracing"""
    print("\n" + "=" * 60)
    print("TEST 5: OTEL Tracing")
    print("=" * 60)
    
    try:
        config = K8sAgentConfig()
        agent = K8sFaultDetectionAgent(config)
        
        print("  Running a test cycle with tracing...")
        result = agent.run_agent_cycle()
        
        print("✓ Agent cycle completed with tracing")
        print(f"\n  Cycle Summary:")
        print(f"    Faults detected: {result['faults_detected']}")
        print(f"    Faults analyzed: {result['faults_analyzed']}")
        print(f"    Remediations attempted: {result['remediations_attempted']}")
        print(f"    Remediations successful: {result['remediations_successful']}")
        
        return True
    except Exception as e:
        print(f"✗ OTEL tracing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dry_run_remediation():
    """Test 6: Test remediation in dry-run mode"""
    print("\n" + "=" * 60)
    print("TEST 6: Dry-Run Remediation")
    print("=" * 60)
    
    try:
        from k8s_fault_agent import RemediationAction
        
        config = K8sAgentConfig()
        agent = K8sFaultDetectionAgent(config)
        
        # Create a sample fault
        sample_fault = FaultDetectionResult(
            timestamp="2024-02-04T10:00:00Z",
            fault_detected=True,
            fault_type=FaultType.POD_CRASH.value,
            affected_resource="pod/test-pod",
            namespace="default",
            severity="high",
            description="Pod is crash looping",
            raw_data={}
        )
        
        print("  Testing dry-run pod restart...")
        result = agent.remediate_fault(
            sample_fault,
            RemediationAction.RESTART_POD,
            dry_run=True
        )
        
        print("✓ Dry-run remediation completed")
        print(f"\n  Remediation Result:")
        print(f"    Action: {result.action_taken}")
        print(f"    Success: {result.success}")
        print(f"    Details: {result.details}")
        
        return True
    except Exception as e:
        print(f"✗ Dry-run remediation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("K8s Fault Detection Agent - Test Suite")
    print("=" * 60)
    
    # Check environment
    required_vars = [
        "OPENAI_API_KEY",
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("\n⚠ WARNING: Missing environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these variables before running tests.")
        print("See .env.example for reference.")
        return False
    
    # Run tests
    tests = [
        ("Configuration", test_configuration),
        ("Kubernetes Connection", test_k8s_connection),
        ("Fault Detection", test_fault_detection),
        ("LLM Analysis", test_llm_analysis),
        ("OTEL Tracing", test_otel_tracing),
        ("Dry-Run Remediation", test_dry_run_remediation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except KeyboardInterrupt:
            print("\n\nTests interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\nUnexpected error in {name}: {e}")
            results.append((name, False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    return all(success for _, success in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
