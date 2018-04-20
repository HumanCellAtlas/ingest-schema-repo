import base64
import json
import os

import boto3
import requests
from github import Github, GithubException


def on_github_push(event, context):
    message = _process_event(event)
    ref = message["ref"]
    if ref == "refs/heads/master":
        repo_name = message["repository"]["full_name"]
        pusher = message["pusher"]["name"]
        api_key = os.environ['API_KEY']
        repo = Github(api_key).get_repo(repo_name)
        notification_message = "Commit to " + ref + " detected on " + repo_name + " by " + pusher
        print(notification_message)
        _send_slack_notification(notification_message, context)
        result = _process_directory(repo, 'json_schema', context)
        result_str = "\n".join(result)
        if len(result) == 0:
            result_message = "No schema changes published"
        else:
            result_message = "New schema changes published:\n" + result_str
            result_message = result_message + _send_schemas_notifications(context)
        print(result_message)
        _send_slack_notification(result_message, context)
    else:
        result = []
    response = {
        "statusCode": 200,
        "body": {
            "created": json.dumps(result)
        }
    }
    return response


def _process_event(event):
    message = json.loads(event["body"])
    return message


def _process_directory(repo, server_path, context):
    print("Processing " + server_path + " in " + repo.name)
    created_list = []
    contents = repo.get_dir_contents(server_path)
    for content in contents:
        if content.type == 'dir':
            created_list.extend(_process_directory(repo, content.path, context))
        else:
            try:
                path = content.path
                file_root, file_extension = os.path.splitext(path)
                if file_extension == '.json':
                    print("- processing: " + path)
                    file_content = repo.get_contents(path)
                    file_data = base64.b64decode(file_content.content)
                    key = _get_schema_key(file_data)
                    if key is None:
                        print("- could not find key for: " + path)
                    else:
                        created = _upload(key, file_data, context)
                        if created:
                            created_list.append(key)
                else:
                    print("- skipping: " + path)
            except(GithubException, IOError) as e:
                print('Error processing %s: %s', content.path, e)
    return created_list


def _upload(key, file_data, context):
    bucket = os.environ['BUCKET']
    s3 = boto3.client('s3')
    if not _key_exists(s3, bucket, key):
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=file_data, ContentType='application/json', ACL='public-read')
            return True
        except Exception as e:
            error_message = 'Error uploading ' + key
            print(error_message, e)
            _send_slack_notification(error_message, context)
    else:
        return False


def _key_exists(s3, bucket, key):
    response = s3.list_objects_v2(
        Bucket=bucket,
        Prefix=key,
    )
    for obj in response.get('Contents', []):
        if obj['Key'] == key:
            return obj['Size']


def _get_schema_key(file_data):
    file_json = json.loads(file_data)
    if 'id' in file_json:
        schema_id = file_json['id']
        key = schema_id.replace(".json", "")
        key = key.replace("https://schema.humancellatlas.org/", "")
    else:
        key = None
    return key


def _send_slack_notification(message, context):
    topic_name = os.environ['TOPIC_NAME']
    account_id = context.invoked_function_arn.split(":")[4]
    if account_id != "Fake":
        print("Sending notification to " + topic_name)
        topic_arn = "arn:aws:sns:" + os.environ['AWS_REGION'] + ":" + account_id + ":" + topic_name
        sns = boto3.client(service_name="sns")
        sns.publish(
            TopicArn=topic_arn,
            Message=message
        )
    else:
        print("Skipping notification: " + message)


def _send_schemas_notifications():
    notification_endpoints_str = os.environ['NOTIFICATION_ENDPOINTS']
    notification_endpoints = notification_endpoints_str.split(',')
    notified = ""
    for notification_endpoint in notification_endpoints:
        print("Notifying: " + notification_endpoint)
        r = requests.post(notification_endpoint)
        if r.status_code == 200:
            notified.join("Successfully notified: " + notification_endpoint + "\n")
        else:
            notified.join("Failed to notify: " + notification_endpoint + " (" + r.status_code + ")" + "\n")
    return notified.strip()


def sns_to_slack(event):
    print(event)
    sns = event['Records'][0]['Sns']
    message = sns['Message']

    webhook_url = os.environ['SLACK_URL']

    payload = {
        'text': message
    }
    r = requests.post(webhook_url, json=payload)
    return r.status_code
