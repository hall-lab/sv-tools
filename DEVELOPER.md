This document is intended to provide guidelines for software developers either maintaining or 
contributing to `svtools` development.

## Installing `svtools` from a git repository
For normal installation, follow the installation instructions in [INSTALL.md](INSTALL.md). Howver, during development it is sometimes desirable to install a version from a git repository directly.

`svtools` is based on `python 2.7`.  First you will need to prepare your python environment.  You should use [pyenv virtualenv][4].
The creation of the pyenv virtual environment and activation looks like this:

    pyenv virtualenv 2.7.9 svtools_install_from_repo-2.7.9
    pyenv activate svtools_install_from_repo-2.7.9

Once you have your python environment set up you will want to check out `svtools` from the [hall-lab github repository][5].  The develop branch contains the bleeding edge version.

    git clone https://github.com/hall-lab/svtools.git svtools_test
    cd svtools_test

**Note:** If you've made local changes or master contains differences from the last tagged release, the version identifier will reflect this.

Or you can discover the release tags on the repo and checkout the latest version

    git tag -l

when you discover the version tag you wish to install you can switch to that version using:

    git checkout tags/v0.2.0b1


**Note:** You can ignore the warning about "You are in 'detached HEAD' state."

OR, you can just proceed to install from master.

Now install the dependencies:

    pip install nose
    pip install coverage
    pip install statsmodels

Installing `statsmodels` can take a few minutes, but it satisfies the requirement for `numpy`, `pandas`, and `scipy`.

In older environments, you may need to specify [`pysam`][10] versions greater than 0.8.1 and less than 0.9.0

    pip install 'pysam>=0.8.1,<0.9.0'

Now we can use `pip` to install `svtools` from within the repo. If you are not already in the directory

    cd svtools_test

or just

    pip install .

Finally we can spot check our `svtools` installation and observe the version number.

    svtools --version

## Contributing

`svtools` development follows the general development model described [here](http://nvie.com/posts/a-successful-git-branching-model/). To contribute code, submit a pull request against the `develop` branch of https://github.com/hall-lab/svtools.

## Releasing a new version

### Tagging a release on github
`svtools` manages its versions using [python-versioneer](https://github.com/warner/python-versioneer). 
New versions are derived and generated from the names of tags in git. To release a new version, all 
that is needed is to tag the correct commit with an annotated tag. Always prepend versions with a 
'v' character.

For example, to release version 0.0.1 from the current commit:
```
git tag -a v0.0.1 -m 'v0.0.1'
git push --tags
```

Next navigate to the github [Releases page](https://github.com/hall-lab/svtools/releases), draft a new 
release using the tag you just generated and add release information (a description of changes made since the last release). This will create an entry on the Github Releases page and upload the release to Zenodo.

### Build a pip package and upload to PyPI
Now that you have a new release, upload the package to [PyPI](https://pypi.python.org/pypi). To do so, you'll need a PyPI account, configuration for both the standard and test PyPI servers and necessary permissions on the `svtools` package. 

These instructions assume you have committed no additional changes after tagging the new release.

1. Build the new release and test by uploading to the PyPI test server.
  
  ```
  pip install --user twine
  python setup.py sdist bdist_wheel
  twine upload --repository-url https://test.pypi.org/legacy/ dist/*
  ```
2. Verify that the package appears and information looks correct at https://test.pypi.org/
3. Verify that the test package installs correctly.

   ```
   pip install --user --extra-index-url https://pypi.org/simple --index-url https://test.pypi.org/simple svtools
   ```
4. Build and upload the package to PyPI itself.
  
  ```
  twine upload dist/*
  ```
5. In a fresh virtual environment, verify that the new package installs.
  
  ```
  pyenv virtualenv 2.7.9 test_new_package
  pyenv activate test_new_package
  pip install svtools
  ```

[1]: http://conda.pydata.org/docs/
[2]: https://pypi.python.org/pypi/pip/
[3]: https://pypi.python.org/pypi
[4]: https://github.com/yyuu/pyenv-virtualenv
[5]: https://github.com/hall-lab/svtools
[6]: https://github.com/hall-lab/svtools/releases
[7]: https://xkcd.com/1168/
[8]: https://github.com/warner/python-versioneer
[9]: https://github.com/hall-lab/svtools/releases
[10]: https://github.com/pysam-developers/pysam
