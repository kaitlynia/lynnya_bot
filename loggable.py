import constants
from util import log


class Loggable:
  log_as = constants.LOG_GENERAL_AS

  def log_info(self, *info):
    log(constants.LOG_PREFIX_INFO, self.log_as, *info)
  def log_done(self, *info):
    log(constants.LOG_PREFIX_DONE, self.log_as, *info)
  def log_error(self, *info):
    log(constants.LOG_PREFIX_ERROR, self.log_as, *info)
