#!/usr/bin/env python3
"""CTZ MCP — AWS CLI Wrapper"""
import json, sys, subprocess

TOOLS = [
    {"name": "aws_s3_list", "description": "List S3 buckets or bucket contents", "inputSchema": {"type": "object", "properties": {"bucket": {"type": "string"}, "prefix": {"type": "string", "default": ""}}, "required": []}},
    {"name": "aws_s3_upload", "description": "Upload file to S3", "inputSchema": {"type": "object", "properties": {"local_path": {"type": "string"}, "bucket": {"type": "string"}, "key": {"type": "string"}}, "required": ["local_path", "bucket", "key"]}},
    {"name": "aws_s3_download", "description": "Download file from S3", "inputSchema": {"type": "object", "properties": {"bucket": {"type": "string"}, "key": {"type": "string"}, "local_path": {"type": "string"}}, "required": ["bucket", "key", "local_path"]}},
    {"name": "aws_ec2_list", "description": "List EC2 instances", "inputSchema": {"type": "object", "properties": {"region": {"type": "string", "default": "us-east-1"}}, "required": []}},
    {"name": "aws_ec2_status", "description": "Get EC2 instance status", "inputSchema": {"type": "object", "properties": {"instance_id": {"type": "string"}, "region": {"type": "string", "default": "us-east-1"}}, "required": ["instance_id"]}},
    {"name": "aws_ec2_start", "description": "Start EC2 instance", "inputSchema": {"type": "object", "properties": {"instance_id": {"type": "string"}, "region": {"type": "string", "default": "us-east-1"}}, "required": ["instance_id"]}},
    {"name": "aws_ec2_stop", "description": "Stop EC2 instance", "inputSchema": {"type": "object", "properties": {"instance_id": {"type": "string"}, "region": {"type": "string", "default": "us-east-1"}}, "required": ["instance_id"]}},
    {"name": "aws_sts_identity", "description": "Get current AWS identity", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "aws_logs_tail", "description": "Tail CloudWatch logs", "inputSchema": {"type": "object", "properties": {"log_group": {"type": "string"}, "lines": {"type": "number", "default": 50}}, "required": ["log_group"]}},
    {"name": "aws_route53_list", "description": "List Route53 hosted zones", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "aws_iam_list_users", "description": "List IAM users", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "aws_sqs_send", "description": "Send message to SQS queue", "inputSchema": {"type": "object", "properties": {"queue_url": {"type": "string"}, "message": {"type": "string"}}, "required": ["queue_url", "message"]}},
    {"name": "aws_sqs_receive", "description": "Receive messages from SQS queue", "inputSchema": {"type": "object", "properties": {"queue_url": {"type": "string"}, "max_messages": {"type": "number", "default": 10}}, "required": ["queue_url"]}},
]

def _run(args, timeout=30):
    try:
        r = subprocess.run(["aws"] + args, capture_output=True, text=True, timeout=timeout)
        return {"stdout": r.stdout[:8000], "stderr": r.stderr[:2000], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"Timed out after {timeout}s"}
    except FileNotFoundError:
        return {"error": "AWS CLI not installed. Install: pip install awscli"}

def handle_s3_list(p):
    if p.get("bucket"):
        r = _run(["s3", "ls", f"s3://{p['bucket']}/{p.get('prefix', '')}"])
    else:
        r = _run(["s3", "ls"])
    return {"output": r.get("stdout", r.get("error", ""))}

def handle_s3_upload(p):
    r = _run(["s3", "cp", p["local_path"], f"s3://{p['bucket']}/{p['key']}"])
    return {"status": "uploaded" if r.get("returncode") == 0 else "failed", "output": r.get("stdout", r.get("error", ""))}

def handle_s3_download(p):
    r = _run(["s3", "cp", f"s3://{p['bucket']}/{p['key']}", p["local_path"]])
    return {"status": "downloaded" if r.get("returncode") == 0 else "failed", "output": r.get("stdout", r.get("error", ""))}

def handle_ec2_list(p):
    region = p.get("region", "us-east-1")
    r = _run(["ec2", "describe-instances", "--region", region, "--query", "Reservations[].Instances[].{ID:InstanceId,State:State.Name,Type:InstanceType,IP:PublicIpAddress}", "--output", "table"])
    return {"output": r.get("stdout", r.get("error", ""))}

def handle_ec2_status(p):
    r = _run(["ec2", "describe-instance-status", "--instance-ids", p["instance_id"], "--region", p.get("region", "us-east-1")])
    return {"output": r.get("stdout", r.get("error", ""))}

def handle_ec2_start(p):
    r = _run(["ec2", "start-instances", "--instance-ids", p["instance_id"], "--region", p.get("region", "us-east-1")])
    return {"status": "starting", "output": r.get("stdout", r.get("error", ""))}

def handle_ec2_stop(p):
    r = _run(["ec2", "stop-instances", "--instance-ids", p["instance_id"], "--region", p.get("region", "us-east-1")])
    return {"status": "stopping", "output": r.get("stdout", r.get("error", ""))}

def handle_sts_identity(p):
    r = _run(["sts", "get-caller-identity"])
    return {"output": r.get("stdout", r.get("error", ""))}

def handle_logs_tail(p):
    r = _run(["logs", "tail", p["log_group"], "--since", f"{p.get('lines', 50)}m", "--format", "short"])
    return {"output": r.get("stdout", r.get("error", ""))[:6000]}

def handle_route53_list(p):
    r = _run(["route53", "list-hosted-zones", "--query", "HostedZones[].{ID:Id,Name:Name,Records:ResourceRecordSetCount}", "--output", "table"])
    return {"output": r.get("stdout", r.get("error", ""))}

def handle_iam_users(p):
    r = _run(["iam", "list-users", "--query", "Users[].{Name:UserName,CreateDate:CreateDate,Arn:Arn}", "--output", "table"])
    return {"output": r.get("stdout", r.get("error", ""))}

def handle_sqs_send(p):
    r = _run(["sqs", "send-message", "--queue-url", p["queue_url"], "--message-body", p["message"]])
    return {"status": "sent" if r.get("returncode") == 0 else "failed", "output": r.get("stdout", r.get("error", ""))}

def handle_sqs_receive(p):
    r = _run(["sqs", "receive-message", "--queue-url", p["queue_url"], "--max-number-of-messages", str(p.get("max_messages", 10)), "--wait-time-seconds", "5"])
    return {"output": r.get("stdout", r.get("error", ""))[:6000]}

HANDLERS = {
    "aws_s3_list": handle_s3_list, "aws_s3_upload": handle_s3_upload, "aws_s3_download": handle_s3_download,
    "aws_ec2_list": handle_ec2_list, "aws_ec2_status": handle_ec2_status,
    "aws_ec2_start": handle_ec2_start, "aws_ec2_stop": handle_ec2_stop,
    "aws_sts_identity": handle_sts_identity, "aws_logs_tail": handle_logs_tail,
    "aws_route53_list": handle_route53_list, "aws_iam_list_users": handle_iam_users,
    "aws_sqs_send": handle_sqs_send, "aws_sqs_receive": handle_sqs_receive,
}

def handle_request(request):
    method, params, req_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}}, "serverInfo": {"name": "ctz-aws", "version": "1.0.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        tool_name = params.get("name", "")
        handler = HANDLERS.get(tool_name)
        if not handler:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
        try:
            result = handler(params.get("arguments", {}))
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

if __name__ == "__main__":
    for line in sys.stdin:
        try:
            r = json.loads(line.strip())
            print(json.dumps(handle_request(r))); sys.stdout.flush()
        except json.JSONDecodeError: continue
