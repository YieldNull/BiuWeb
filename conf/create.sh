#!/bin/bash

# Build A Website With Python-Flask and Nginx
# Doc: http://yieldnull.com/blog/0b2e0169df807bec78b3ad3eea87105a2e5299c6/

# Author: YieldNull
# Updated On: 2016/02/25

if [ ! $# = 3 ] ; then
    echo "Args: project_name port domain_name"
    exit
fi

project=$1  # project name
port=$2  # project port
domain=$3  # domain name

# program directory
directory="/srv/www/$1"
sudo mkdir -p $directory/app
sudo mkdir -p $directory/log
sudo mkdir -p $directory/files

# nginx
nginx_file="/etc/nginx/sites-available/$project"
nginx_conf="server {
    listen      80;

    root  $directory/app;
    access_log $directory/log/access_log;
    error_log  $directory/log/error_log;

    client_max_body_size 0;

    server_name $3;

    location ~ ^\/static\/.*$ {
        root $directory/app/;
    }

    location ~ ^\/files\/.*?\/(.*)$ {
	    root $directory/;
	    add_header Content-Disposition 'attachment; filename="'$1'"';
    }

    location / {
        proxy_pass       http://127.0.0.1:$port;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}"

echo "$nginx_conf" | sudo tee $nginx_file
sudo chmod 644 $nginx_file
sudo ln -s $nginx_file /etc/nginx/sites-enabled/$project

# gunicorn
gunicorn_conf="
bind = '127.0.0.1:$port'
workers = 4
worker_class = 'gevent'
timeout = 60
keep_alive = 75
"
gunicorn_file="$directory/gunicorn.py"

echo "$gunicorn_conf" | sudo tee $gunicorn_file

# supervisor
supervisor_file="/etc/supervisor/conf.d/$project.conf"
supervisor_conf="
[program:$project]
command         = $directory/venv/bin/gunicorn -c $directory/gunicorn.py wsgi:app
directory       = $directory/app
user            = $USER
startsecs       = 3

redirect_stderr         = true
stdout_logfile_maxbytes = 50MB
stdout_logfile_backups  = 10
stdout_logfile          = $directory/log/supervisor.log"

echo "$supervisor_conf" | sudo tee $supervisor_file

# virtualenv
sudo virtualenv $directory/venv
sudo chmod -R 777 $directory/venv
source $directory/venv/bin/activate
pip3 install gunicorn gevent
deactivate
sudo chmod -R 755 $directory/venv
sudo chown -R $USER:$USER $directory
sudo chown -R git:git $directory/app
sudo chown -R git:git $directory/venv

# git
git_dir="/srv/git/$project.git"
hook_file="$git_dir/hooks/post-receive"
hook_shell="#!/bin/bash
read oldrev newrev refname

if [ "'"$refname"'" = "\"refs/heads/master\"" ] ; then
    # if master branch is pushed
    GIT_WORK_TREE=$directory/app git checkout -f
    source $directory/venv/bin/activate
    pip3 install -r $directory/app/requirements.txt
    deactivate
    supervisorctl reload $project
fi
"

sudo mkdir -p /srv/git
sudo git init --bare $git_dir
echo "$hook_shell" | sudo tee $hook_file

sudo chmod 755 $hook_file
sudo chown -R git:git $git_dir
sudo chown -R $USER:$USER $directory/app
git clone git@127.0.0.1:/srv/git/$project.git $directory/app
sudo chown -R git:git $directory/app

sudo service nginx restart
sudo supervisorctl reload

