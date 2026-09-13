"""Database maintenance and query explanation utilities."""
from __future__ import annotations

import traceback
from typing import Any, Dict, List

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.time_utils import utc_now

from . import _connection
from ._connection import (
    _DB_LOCK,
    _db_cursor,
    _init_db,
)


def maintain_database(vacuum: bool = True, analyze: bool = True) -> Dict[str, Any]:
    """
    Perform database maintenance operations for improved performance.
    
    Args:
        vacuum: Whether to run VACUUM to reclaim unused space
        analyze: Whether to run ANALYZE to update statistics for query optimization
        
    Returns:
        Dictionary with operation results
    """
    results = {"success": True, "operations": []}
    
    if not _connection._DB_CONN:
        _init_db()
    
    try:
        with _DB_LOCK:
            if vacuum:
                start_time = utc_now()
                _connection._DB_CONN.execute("VACUUM")  # type: ignore[union-attr]
                end_time = utc_now()
                duration = (end_time - start_time).total_seconds()
                results["operations"].append({
                    "operation": "VACUUM", 
                    "success": True,
                    "duration_seconds": duration
                })
                print_and_log(f"[+] Database VACUUM completed in {duration:.2f} seconds", LOG__DEBUG)
                
            if analyze:
                start_time = utc_now()
                _connection._DB_CONN.execute("ANALYZE")  # type: ignore[union-attr]
                end_time = utc_now()
                duration = (end_time - start_time).total_seconds()
                results["operations"].append({
                    "operation": "ANALYZE", 
                    "success": True,
                    "duration_seconds": duration
                })
                print_and_log(f"[+] Database ANALYZE completed in {duration:.2f} seconds", LOG__DEBUG)
                
        # Get database statistics
        with _db_cursor() as cur:
            # Get total row counts
            counts = {}
            for table in ["devices", "services", "characteristics", "descriptors",
                         "char_history", "adv_reports", "classic_services",
                         "media_players", "media_transports", "aoi_analysis",
                         "sdp_records", "device_type_evidence", "pbap_metadata"]:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    counts[table] = cur.fetchone()[0]
                except Exception:
                    counts[table] = -1
                    
            # Get database size
            cur.execute("PRAGMA page_count")
            page_count = cur.fetchone()[0]
            cur.execute("PRAGMA page_size")
            page_size = cur.fetchone()[0]
            db_size = page_count * page_size
            
            results["statistics"] = {
                "row_counts": counts,
                "database_size_bytes": db_size,
                "database_size_mb": round(db_size / (1024 * 1024), 2)
            }
            
        return results
        
    except Exception as e:
        print_and_log(f"[-] Database maintenance error: {e}", LOG__DEBUG)
        print_and_log(traceback.format_exc(), LOG__DEBUG)
        results["success"] = False
        results["error"] = str(e)
        return results

def explain_query(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """
    Get the execution plan for a SQL query for performance debugging.
    
    Args:
        query: SQL query to explain (must be a single SELECT statement)
        params: Query parameters
        
    Returns:
        List of dictionaries describing the query execution plan
    """
    if not _connection._DB_CONN:
        _init_db()

    stripped = query.strip().rstrip(";")
    if ";" in stripped or not stripped.upper().startswith("SELECT"):
        raise ValueError("explain_query only accepts a single SELECT statement")

    try:
        with _DB_LOCK, _db_cursor() as cur:
            cur.execute(f"EXPLAIN QUERY PLAN {stripped}", params)
            plan = cur.fetchall()
            
            # Format the plan as a list of dictionaries
            result = []
            for row in plan:
                result.append({
                    "id": row["id"],
                    "parent": row["parent"],
                    "notused": row["notused"],
                    "detail": row["detail"]
                })
            
            return result
    except Exception as e:
        print_and_log(f"[-] Error explaining query: {e}", LOG__DEBUG)
        return [{"error": str(e)}]
