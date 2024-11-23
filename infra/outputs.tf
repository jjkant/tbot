
output "ssm_parameters" {
  value = [
    aws_ssm_parameter.mongodb_connection_string.name,
    aws_ssm_parameter.sqs_input_queue_url.name,
    aws_ssm_parameter.sqs_output_queue_url.name
  ]
}

output "sqs_queue_urls" {
  value = {
    input_queue_url  = aws_sqs_queue.input_queue.id
    output_queue_url = aws_sqs_queue.output_queue.id
  }
}

output "ec2_public_ip" {
  value = aws_instance.twitch_bot_ec2.public_ip
}


