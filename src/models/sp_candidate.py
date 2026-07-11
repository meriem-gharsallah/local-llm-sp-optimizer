"""
sp_candidate.py - Data class for optimization candidates
"""

from dataclasses import dataclass


@dataclass
class SPCandidate:
    """Candidate for optimization"""
    sp_name: str
    score: int
    execution_count: int
    avg_elapsed_ms: float
    avg_logical_reads: float
    avg_cpu_ms: float
    total_hours_wasted: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "sp_name": self.sp_name,
            "score": self.score,
            "execution_count": self.execution_count,
            "avg_elapsed_ms": self.avg_elapsed_ms,
            "avg_logical_reads": self.avg_logical_reads,
            "avg_cpu_ms": self.avg_cpu_ms,
            "total_hours_wasted": self.total_hours_wasted,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SPCandidate':
        """Create instance from dictionary"""
        return cls(
            sp_name=data["sp_name"],
            score=data["score"],
            execution_count=data["execution_count"],
            avg_elapsed_ms=data["avg_elapsed_ms"],
            avg_logical_reads=data["avg_logical_reads"],
            avg_cpu_ms=data["avg_cpu_ms"],
            total_hours_wasted=data["total_hours_wasted"],
        )