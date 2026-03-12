"""
Static Analysis Sweep for API Cost Optimization
Uses AST parsing to identify inefficient LLM usage patterns.
"""
import ast
import inspect
import os
from typing import Dict, List, Tuple, Any, Optional
import logging
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class CostFinding:
    """Represents a potential cost optimization finding"""
    severity: str  # "HIGH", "MEDIUM", "LOW"
    file_path: str
    line_number: int
    description: str
    suggested_fix: str
    estimated_savings: Optional[str] = None

class APICostAnalyzer(ast.NodeVisitor):
    """AST visitor for detecting inefficient API usage patterns"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.findings: List[CostFinding] = []
        self.current_function = None
        
    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """Track current function context"""
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = None
        
    def visit_For(self, node: ast.For) -> Any:
        """Check for API calls in loops"""
        self._check_node_for_api_calls(node, "loop")
        self.generic_visit(node)
        
    def visit_While(self, node: ast.While) -> Any:
        """Check for API calls in while loops"""
        self._check_node_for_api_calls(node, "while loop")
        self.generic_visit(node)
        
    def visit_Call(self, node: ast.Call) -> Any:
        """Check for OpenAI API calls and inefficient patterns"""
        # Check for OpenAI calls
        if self._is_openai_call(node):
            # Check if in loop
            if self._is_in_loop_context():
                self.findings.append(CostFinding(
                    severity="HIGH",
                    file_path=self.file_path,
                    line_number=node.lineno,
                    description="LLM API call inside loop",
                    suggested_fix="Consider batching requests or moving API call outside loop",
                    estimated_savings="Potential 60-90% reduction"
                ))
            
            # Check for large context being passed
            if self._has_large_context_argument(node):
                self.findings.append(CostFinding(
                    severity="MEDIUM",
                    file_path=self.file_path,
                    line_number=node.lineno,
                    description="Potential context inefficiency",
                    suggested_fix="Use context compression or caching",
                    estimated_savings="Potential 20-40% reduction"
                ))
        
        self.generic_visit(node)
    
    def _is_openai_call(self, node: ast.Call) -> bool:
        """Check if this is an OpenAI API call"""
        try:
            # Check for openai.ChatCompletion.create or similar
            if isinstance(node.func, ast.Attribute):
                if hasattr(node.func.value, 'id'):
                    if node.func.value.id == 'openai' and node.func.attr in ['create', 'ChatCompletion']:
                        return True
                # Check for openai.ChatCompletion.create chain
                if isinstance(node.func.value, ast.Attribute):
                    if node.func.value.attr == 'ChatCompletion':
                        return True
        except Exception as e:
            logger.debug(f"Error checking OpenAI call: {e}")
        return False
    
    def _is_in_loop_context(self) -> bool:
        """Check if current node is within a loop"""
        # Simplified check - in real implementation would track context stack
        return False  # Placeholder - would implement proper context tracking
    
    def _has_large_context_argument(self, node: ast.Call) -> bool:
        """Check for large context/messages arrays"""
        try:
            for keyword in node.keywords:
                if keyword.arg == 'messages' and isinstance(keyword.value, ast.List):
                    if len(keyword.value.elts) > 5:  # Arbitrary threshold
                        return True
                if keyword.arg == 'prompt' and isinstance(keyword.value, ast.Str):
                    if len(keyword.value.s) > 1000:
                        return True
        except Exception as e:
            logger.debug(f"Error checking context size: {e}")
        return False
    
    def _check_node_for_api_calls(self, node: Any, context: str) -> None:
        """Check a node for API calls"""
        # This would be implemented with a more sophisticated visitor pattern
        pass

def analyze_file(file_path: str) -> List[CostFinding]:
    """Analyze a single Python file for cost inefficiencies"""
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        analyzer = APICostAnalyzer(file_path)
        analyzer.visit(tree)
        
        logger.info(f"Analyzed {file_path}, found {len(analyzer.findings)} issues")
        return analyzer.findings
        
    except SyntaxError as e:
        logger.error(f"Syntax error in {file_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error analyzing {file_path}: {e}")
        return []

def analyze_directory(directory_path: str) -> Dict[str, List[CostFinding]]:
    """Recursively analyze all Python files in directory"""
    results = {}
    
    if not os.path.exists(directory_path):
        logger.error(f"Directory not found: {directory_path}")
        return results
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                findings = analyze_file(full_path)
                if findings:
                    results[full_path] = findings
    
    return results

def export_findings_to_firestore(findings: Dict[str, List[CostFinding]]) -> None:
    """Export analysis findings to Firestore for dashboard"""
    try:
        import firebase_admin
        from firebase_admin import firestore
        
        db = firestore.client()
        batch = db.batch()
        
        for file_path, file_findings in findings.items():
            doc_ref = db.collection('cost_audit').document()
            batch.set(doc_ref, {
                'file_path': file_path,
                'findings': [f.__dict__ for f in file_findings],
                'timestamp': firestore.SERVER_TIMESTAMP,
                'total_findings': len(file_findings),
                'high_severity_count': sum(1 for f in file_findings if f.severity == "HIGH")
            })
        
        batch.commit()
        logger.info(f"Exported {len(findings)} files to Firestore")
        
    except ImportError:
        logger.warning("firebase_admin not installed, skipping Firestore export")
    except Exception as e:
        logger.error(f"Error exporting to Firestore: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test the analyzer
    import sys
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = "."
    
    if os.path.isdir(target):
        results = analyze_directory(target)
    else:
        results = {target: analyze_file(target)}
    
    # Print summary
    total_findings = sum(len(v) for v in results.values())
    high_findings = sum(
        sum(1 for f in findings if f.severity == "HIGH") 
        for findings in results.values()
    )
    
    print(f"\n=== Cost Analysis Complete ===")
    print(f"Files analyzed: {len(results)}")
    print(f"Total findings: {total_findings}")
    print(f"High severity: {high_findings}")
    
    # Export if available
    try:
        export_findings_to_firestore(results)
        print("Results exported to Firestore")
    except:
        print("Could not export to Firestore (dependency missing)")