#!/usr/bin/env python3
"""
CHAOS TYPE ZERO MCP — ML Pipeline Server
Tools: ml_train, ml_predict, ml_evaluate, ml_list, ml_delete, ml_status
"""

import json
import sys
try:
    import numpy as np
except ImportError:
    np = None
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from bridge_core.ml_pipeline import get_ml_pipeline

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "ctz-ml"
SERVER_VERSION = "1.0.0"

TOOLS = [
    {
        "name": "ml_train",
        "description": "Train a classification or regression model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["classifier", "regressor"], "description": "Model type"},
                "model": {"type": "string", "description": "Algorithm: random_forest, gradient_boosting, svm, logistic_regression, linear"},
                "X": {"type": "array", "description": "Training features (2D array)"},
                "y": {"type": "array", "description": "Training labels"},
                "test_size": {"type": "number", "description": "Test split ratio (default 0.2)"},
            },
            "required": ["type", "X", "y"],
        },
    },
    {
        "name": "ml_predict",
        "description": "Make predictions using a saved model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID from training"},
                "X": {"type": "array", "description": "Input features (2D array)"},
            },
            "required": ["model_id", "X"],
        },
    },
    {
        "name": "ml_list",
        "description": "List all saved models",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ml_delete",
        "description": "Delete a saved model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID to delete"},
            },
            "required": ["model_id"],
        },
    },
    {
        "name": "ml_status",
        "description": "Get ML pipeline status",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_request(request):
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        pipeline = get_ml_pipeline()

        try:
            if tool_name == "ml_train":
                X = np.array(args["X"])
                y = np.array(args["y"])
                if args.get("type") == "regressor":
                    result = pipeline.train_regressor(X, y, model_type=args.get("model", "random_forest"))
                else:
                    result = pipeline.train_classifier(X, y, model_type=args.get("model", "random_forest"))

            elif tool_name == "ml_predict":
                X = np.array(args["X"])
                result = pipeline.predict(args["model_id"], X)

            elif tool_name == "ml_list":
                result = pipeline.list_models()

            elif tool_name == "ml_delete":
                result = pipeline.delete_model(args["model_id"])

            elif tool_name == "ml_status":
                result = pipeline.get_status()

            else:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}

            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
            }}

        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}]
            }}

    elif method == "notifications/initialized":
        return None

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response:
                print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}), flush=True)
