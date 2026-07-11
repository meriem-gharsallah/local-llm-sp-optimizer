"""
optimization_result.py - Data class for optimization results
"""

from dataclasses import dataclass


@dataclass
class OptimizationResult:
    """Result of SP optimization"""
    sp_name: str
    score: int
    execution_count: int
    avg_elapsed_ms: float
    total_hours_wasted: float
    status: str  # success, error, skipped
    diagnostic: str = ""
    optimized_code: str = ""
    explanation: str = ""
    estimated_gain: int = 0
    risk: str = "LOW"
    duration_seconds: float = 0.0
    error: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "sp_name": self.sp_name,
            "score": self.score,
            "execution_count": self.execution_count,
            "avg_elapsed_ms": self.avg_elapsed_ms,
            "total_hours_wasted": self.total_hours_wasted,
            "status": self.status,
            "diagnostic": self.diagnostic,
            "optimized_code": self.optimized_code,
            "explanation": self.explanation,
            "estimated_gain": self.estimated_gain,
            "risk": self.risk,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'OptimizationResult':
        """Create instance from dictionary"""
        return cls(
            sp_name=data["sp_name"],
            score=data["score"],
            execution_count=data["execution_count"],
            avg_elapsed_ms=data["avg_elapsed_ms"],
            total_hours_wasted=data["total_hours_wasted"],
            status=data["status"],
            diagnostic=data.get("diagnostic", ""),
            optimized_code=data.get("optimized_code", ""),
            explanation=data.get("explanation", ""),
            estimated_gain=data.get("estimated_gain", 0),
            risk=data.get("risk", "LOW"),
            duration_seconds=data.get("duration_seconds", 0.0),
            error=data.get("error", ""),
        )