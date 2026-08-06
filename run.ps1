using namespace System.Net

param($Request, $TriggerMetadata)

$vestaboardToken = $env:VESTABOARD_TOKEN

if ([string]::IsNullOrWhiteSpace($vestaboardToken)) {
    Push-OutputBinding -Name Response -Value ([HttpResponseContext]@{
        StatusCode = [HttpStatusCode]::InternalServerError
        Headers    = @{ "Content-Type" = "application/json" }
        Body       = @{
            error = "The Vestaboard API token has not been configured."
        } | ConvertTo-Json
    })
    return
}

$message = $Request.Body.message

if ([string]::IsNullOrWhiteSpace($message)) {
    Push-OutputBinding -Name Response -Value ([HttpResponseContext]@{
        StatusCode = [HttpStatusCode]::BadRequest
        Headers    = @{ "Content-Type" = "application/json" }
        Body       = @{
            error = "Provide a non-empty message property."
            example = @{
                message = "Hello Andrew"
            }
        } | ConvertTo-Json -Depth 3
    })
    return
}

$headers = @{
    "X-Vestaboard-Token" = $vestaboardToken
}

$vestaboardBody = @{
    text = $message
} | ConvertTo-Json

try {
    $vestaboardResponse = Invoke-RestMethod `
        -Uri "https://cloud.vestaboard.com/" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $vestaboardBody

    Push-OutputBinding -Name Response -Value ([HttpResponseContext]@{
        StatusCode = [HttpStatusCode]::OK
        Headers    = @{ "Content-Type" = "application/json" }
        Body       = @{
            success = $true
            message = $message
            vestaboardResponse = $vestaboardResponse
        } | ConvertTo-Json -Depth 5
    })
}
catch {
    Write-Error $_

    $statusCode = [HttpStatusCode]::BadGateway

    Push-OutputBinding -Name Response -Value ([HttpResponseContext]@{
        StatusCode = $statusCode
        Headers    = @{ "Content-Type" = "application/json" }
        Body       = @{
            success = $false
            error   = "Vestaboard rejected the request."
            detail  = $_.Exception.Message
        } | ConvertTo-Json
    })
}