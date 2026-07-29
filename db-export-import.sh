#!/bin/bash

set -e
set -o pipefail

# check if gum is installed
if ! command -v gum &> /dev/null; then
  echo "gum is required. Install it with 'brew install gum'"
  exit 1
fi

# check if jq is installed
if ! command -v jq &> /dev/null; then
  if gum confirm "jq is required. Do you want to install it?"; then
    echo "Installing jq..."
    brew install jq
  else
    echo "Aborting..."
    echo "jq is required. Install it with 'brew install jq'"
    exit 1
  fi
fi

config_file="${DB_DUMP_CONFIG:-${HOME}/.config/toolbox/db-dump.json}"

action=$(gum choose --header="What do you want to do?" "export" "import")

# create config dir if not exists
if [[ ! -d $(dirname $config_file) ]]; then
  mkdir -p $(dirname $config_file)
fi

# create config file if not exists
if [[ ! -f $config_file ]]; then
  echo "{}" > $config_file
fi

# read config file db_connections dict
db_connections=$(jq -r '.dbConnections | to_entries' $config_file)

# get db connection keys as array
db_connection_names=$(jq -r '.dbConnections | keys[]' "$config_file")
echo $db_connection_names

connection=$(gum choose --header="source:" $db_connection_names "+ new connection")

if [[ "$connection" == "+ new connection" ]]; then
  name=$(gum input --prompt "Name? " --placeholder "prod")
  name=$(echo $name | tr -d '[:space:]')

  if [[ " ${db_connection_names[@]} " =~ " ${name} " ]]; then
    echo "Name '${name}' already exists."
      override=$(gum choose --header="Do you want to override it?" "yes" "no")
      if [[ $override == "no" ]]; then
          echo "Aborting..."
          exit 0
      fi
  fi

  connection_string=$(gum input --width 255 --prompt "Connection string? " --placeholder "postgresql://...")
  connection_string=$(echo $connection_string | tr -d '[:space:]')

  if [ -z "$connection_string" ]; then
    echo "no connection string provided. Exiting..."
    exit 1
  fi

  if [[ $override == "yes" ]]; then
    echo "replacing $name"
    jq ".dbConnections.${name} = \"$connection_string\"" $config_file> $config_file.tmp
  else
    echo "adding $name $connection_string"
    if [[ $(jq 'has("dbConnections")' $config_file) ]]; then
      jq ".dbConnections += {\"$name\": \"$connection_string\"}" $config_file > $config_file.tmp
    else
      jq ".dbConnections = {\"$name\": \"$connection_string\"}" $config_file > $config_file.tmp
    fi
  fi
  mv $config_file.tmp $config_file
else
  name=$connection
  connection_string=$(jq -r ".dbConnections.$connection" $config_file)
fi

if [[ $action == "export" ]]; then
  filename="${HOME}/Downloads/dump-${name}-$(date +%Y-%m-%dT%H:%M:%S).dump"
  gum spin --show-error --title "Exporting from ${name}..." -- pg_dump -Fc --no-owner --no-acl $connection_string -f $filename
  echo "Exported to: $filename"
else
  # check if connection string contains 0.0.0.0 or localhost
  if [[ "$connection_string" != *"localhost"* && "$connection_string" != *"0.0.0.0"* ]]; then
    echo "Aborting, importing is only allowed for localhost."
    exit 1
  fi
  filename=$(gum input --width 255 --prompt "Path to dump file? " --placeholder "/path/to/dump.dump")

  if [[ ! -f $filename ]]; then
    echo "File not found: $filename"
    exit 1
  fi

  if ! echo "$connection_string" | grep -q "sslmode=disable"; then
    if [[ "$connection_string" =~ "\?" ]]; then
      connection_string+='&sslmode=disable'
    else
      connection_string+='?sslmode=disable'
    fi
  fi

  gum confirm "This will reset your database. Continue?" && \
    dbmate --url $connection_string drop && \
    dbmate --url $connection_string create && \
    gum spin --show-error --title "Importing ${filename} to ${name} (${connection_string})..." -- pg_restore --no-owner --no-acl -d $connection_string $filename && \
    dbmate --url $connection_string --no-dump-schema migrate && \
    echo "Imported $filename to $name"
fi
